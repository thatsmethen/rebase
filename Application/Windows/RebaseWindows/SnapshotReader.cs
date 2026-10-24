using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;

namespace Rebase.Windows;

public sealed record LoadedSnapshot(float[] Samples, uint SampleRate, ulong Frames);
public static class SnapshotReader
{
    // Transport adapter for the helper's own output, never a project-media decoder.
    public static LoadedSnapshot Read(RenderSnapshot info, string requestedPath, ulong revision, SourceEventView? sourceEvent = null,
        ProjectView? project = null, string mode = SourceAuditionMode.Original)
    {
        ValidateContext(info, sourceEvent);
        if (sourceEvent is not null)
        {
            if (project is null) throw new InvalidDataException("The source render omitted its project context.");
            SourceAuditionManifest.Validate(info, requestedPath, revision, sourceEvent, project, mode);
        }
        if (info.Revision != revision || !Path.GetFullPath(info.Path).Equals(Path.GetFullPath(requestedPath), StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("The rendered snapshot does not belong to this document revision.");
        var emptySourceEnd = sourceEvent is not null && info.Frames == 0 && info.StartFrame == info.TotalFrames && info.TotalFrames > 0;
        if ((!emptySourceEnd && info.Frames == 0) || info.Frames > 32_000_000 || info.Channels != 2 ||
            info.SampleRate < 8000 || info.SampleRate > 192000 || info.SampleRate != Math.Truncate(info.SampleRate) ||
            info.WavBytes < 44 || info.WavBytes > 256_000_256)
            throw new InvalidDataException("The rendered snapshot exceeds the supported stereo transport format.");
        var file = new FileInfo(requestedPath);
        if ((file.Attributes & FileAttributes.ReparsePoint) != 0 || (ulong)file.Length != info.WavBytes)
            throw new InvalidDataException("The snapshot file size or file type changed.");
        var data = File.ReadAllBytes(requestedPath);
        if ((ulong)data.Length != info.WavBytes || !Convert.ToHexString(SHA256.HashData(data)).Equals(info.Sha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("The snapshot does not match the renderer's SHA-256.");
        return Decode(data, (uint)info.SampleRate, info.Frames, emptySourceEnd);
    }
    public static void ValidateContext(RenderSnapshot info, SourceEventView? sourceEvent)
    {
        static bool Digest(string? value) => value is { Length: 64 } && value.All(char.IsAsciiHexDigit);
        if (sourceEvent is null)
        {
            if (info.Kind != "project" || info.EventID is not null || info.SourceSHA256 is not null || info.MediaSHA256 is not null ||
                info.Mode is not null || info.ManifestPath is not null || info.ManifestSHA256 is not null || info.ManifestBytes is not null ||
                info.StartFrame is not null || info.TotalFrames is not null)
                throw new InvalidDataException("The renderer returned a different playback context instead of a project mix.");
        }
        else if (info.Kind != "sourceEvent" || !string.Equals(info.EventID, sourceEvent.Id, StringComparison.OrdinalIgnoreCase) ||
            !Digest(sourceEvent.SourceSHA256) || !Digest(sourceEvent.MediaSHA256) ||
            !string.Equals(info.SourceSHA256, sourceEvent.SourceSHA256, StringComparison.OrdinalIgnoreCase) ||
            !string.Equals(info.MediaSHA256, sourceEvent.MediaSHA256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("The rendered source event does not match the selected event and its attached media.");
    }
    public static LoadedSnapshot Decode(byte[] data, uint rate, ulong frames, bool allowEmptySourceEnd = false)
    {
        static uint U32(byte[] b, int i) => BinaryPrimitives.ReadUInt32LittleEndian(b.AsSpan(i, 4));
        static ushort U16(byte[] b, int i) => BinaryPrimitives.ReadUInt16LittleEndian(b.AsSpan(i, 2));
        static string Tag(byte[] b, int i) => Encoding.ASCII.GetString(b, i, 4);
        if (data.Length < 12 || Tag(data, 0) != "RIFF" || Tag(data, 8) != "WAVE" || (ulong)U32(data, 4) + 8 != (ulong)data.Length)
            throw new InvalidDataException("The renderer did not return a complete RIFF/WAVE snapshot.");
        int format = -1, formatLength = 0, payload = -1, payloadLength = 0;
        int cursor = 12;
        while (cursor < data.Length)
        {
            if (data.Length - cursor < 8) throw new InvalidDataException("Truncated snapshot chunk.");
            var tag = Tag(data, cursor); var length = U32(data, cursor + 4); cursor += 8;
            if (length > data.Length - cursor) throw new InvalidDataException("Truncated snapshot data.");
            if (tag == "fmt ") { if (format >= 0) throw new InvalidDataException("Duplicate snapshot format."); format = cursor; formatLength = (int)length; }
            if (tag == "data") { if (payload >= 0) throw new InvalidDataException("Duplicate snapshot samples."); payload = cursor; payloadLength = (int)length; }
            cursor = checked(cursor + (int)length + (int)(length & 1));
            if (cursor > data.Length) throw new InvalidDataException("Missing snapshot padding.");
        }
        if (format < 0 || payload < 0 || formatLength < 16 || U16(data, format) != 3 || U16(data, format + 2) != 2 ||
            U32(data, format + 4) != rate || U32(data, format + 8) != rate * 8 || U16(data, format + 12) != 8 ||
            U16(data, format + 14) != 32 || (frames == 0 && !allowEmptySourceEnd) || frames > 32_000_000 || (ulong)payloadLength != frames * 8)
            throw new InvalidDataException("The snapshot is not the expected Float32 stereo render.");
        var samples = new float[checked((int)frames * 2)];
        for (int i = 0; i < samples.Length; ++i)
        {
            samples[i] = BitConverter.Int32BitsToSingle(BinaryPrimitives.ReadInt32LittleEndian(data.AsSpan(payload + i * 4, 4)));
            if (!float.IsFinite(samples[i])) throw new InvalidDataException("The snapshot contains a nonfinite sample.");
        }
        return new LoadedSnapshot(samples, rate, frames);
    }
}
