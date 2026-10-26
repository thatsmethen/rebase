using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using static Rebase.Windows.SourceStreamWire;

namespace Rebase.Windows;

// One record is retained at a time. Payload bounds are resource limits, never
// duration limits. Logical output-stage partitions are checked but not rerun.
public sealed class SourceStreamReader(Stream input) : IDisposable
{
    private readonly IncrementalHash pcmHash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
    private SourceStreamAdmission? admission;
    private ulong sequence, absoluteFrame, logicalBlock, logicalOffset, logicalFrames;
    private bool ended, failed;
    public ulong ReceivedFrames { get; private set; }
    public string? PCMHash { get; private set; }

    public async Task<SourceStreamAdmission> Admit(SourceStreamTicket ticket, SourceEventView selected,
        ProjectView project, CancellationToken cancellation)
    {
        Require(admission is null && !ended && !failed, "Source admission was repeated.");
        try
        {
            var record = await ReadRecord(cancellation);
            using var document = record.Document;
            var data = document.RootElement;
            if (record.Kind == 4) ThrowFailure(data, ticket.Generation);
            Require(record.Kind == 1 && record.Payload.Length == 0 && Text(data, "schema") == "rebase.source-stream-admission.v1" &&
                SameID(Text(data, "generation"), ticket.Generation) && Integer(data, "revision") == ticket.Revision &&
                SameID(Text(data, "eventID"), ticket.EventID) && Text(data, "mode") == ticket.Mode &&
                Integer(data, "sampleRate") == ticket.SampleRate && Integer(data, "startFrame") == ticket.StartFrame &&
                Integer(data, "totalFrames") == ticket.TotalFrames && Integer(data, "frames") == ticket.Frames &&
                Integer(data, "channels") == 2 && Text(data, "proofSHA256") == ticket.ProofSHA256,
                "The admitted source stream differs from its ticket.");
            var maximum = Integer(data, "maximumChunkFrames");
            Require(maximum is > 0 and <= 65536 && maximum <= ticket.MaximumChunkFrames, "Invalid source chunk bound.");
            var proof = Property(data, "proof");
            var bytes = Encoding.UTF8.GetBytes(proof.GetRawText());
            Require(Text(proof, "schema") == "rebase.source-stream-proof.v1" &&
                Convert.ToHexStringLower(SHA256.HashData(bytes)) == ticket.ProofSHA256,
                "The complete source preparation proof failed its hash check.");
            foreach (var forbidden in new[] { "wavFileName", "wavBytes", "wavSHA256", "maximumFrames" })
                Require(!proof.TryGetProperty(forbidden, out _), "A stream proof used snapshot export fields.");
            SourceAuditionManifest.ValidatePreparation(proof, ticket.Revision, selected, project, ticket.Mode,
                ticket.SampleRate, ticket.StartFrame, ticket.TotalFrames, ticket.Frames);
            admission = new(ticket, (uint)maximum, proof.Clone());
            absoluteFrame = ticket.StartFrame;
            return admission;
        }
        catch { failed = true; throw; }
    }

    public async Task<SourceStreamChunk?> Read(CancellationToken cancellation)
    {
        Require(admission is not null && !failed && !ended, "The source stream is not accepting records.");
        try
        {
            var record = await ReadRecord(cancellation);
            using var document = record.Document;
            var data = document.RootElement;
            var ticket = admission!.Ticket;
            if (record.Kind == 4) ThrowFailure(data, ticket.Generation);
            Require(SameID(Text(data, "generation"), ticket.Generation), "A source record belongs to an old generation.");
            if (record.Kind == 3)
            {
                var digest = Text(data, "pcmSHA256");
                var observed = Convert.ToHexStringLower(pcmHash.GetHashAndReset());
                Require(record.Payload.Length == 0 && logicalOffset == 0 && absoluteFrame == ticket.TotalFrames &&
                    Integer(data, "nextSequence") == sequence && Integer(data, "nextAbsoluteFrame") == absoluteFrame &&
                    Integer(data, "frames") == ReceivedFrames && ReceivedFrames == ticket.Frames &&
                    Digest(digest) && digest == observed, "The source stream ended with incomplete or changed PCM.");
                // Terminal EOF is a record, followed by real pipe EOF. Extra
                // records or bytes cannot silently begin another generation.
                var extra = new byte[1];
                Require(await input.ReadAsync(extra, cancellation) == 0, "Unexpected data followed source EOF.");
                PCMHash = observed; ended = true; return null;
            }
            Require(record.Kind == 2, "Unexpected source stream record ordering.");
            var frames = Integer(data, "frames");
            var count = Integer(data, "logicalFrames");
            Require(Integer(data, "sequence") == sequence && Integer(data, "absoluteFrame") == absoluteFrame &&
                frames > 0 && frames <= admission.MaximumChunkFrames && frames <= ticket.TotalFrames - absoluteFrame &&
                record.Payload.Length == (long)frames * 8 && Integer(data, "logicalBlock") == logicalBlock &&
                Integer(data, "logicalOffset") == logicalOffset && count is > 0 and <= 16_000_000 && count <= ticket.Frames &&
                logicalOffset <= count && frames <= count - logicalOffset,
                "The source stream skipped, repeated or changed a PCM partition.");
            if (logicalOffset == 0) logicalFrames = count;
            Require(logicalFrames == count, "The source stream changed its logical output block.");
            var digestValue = Text(data, "sha256");
            Require(Digest(digestValue) && Convert.ToHexStringLower(SHA256.HashData(record.Payload)) == digestValue,
                "The source PCM payload failed its hash check.");
            var samples = new float[checked((int)frames * 2)];
            for (var i = 0; i < samples.Length; i++)
            {
                var bits = BinaryPrimitives.ReadUInt32LittleEndian(record.Payload.AsSpan(i * 4, 4));
                // Classify IEEE words without arithmetic to retain signed zero
                // and subnormal sample bits through an equal-rate device path.
                Require((bits & 0x7f800000u) != 0x7f800000u, "The source stream contains a nonfinite sample.");
                samples[i] = BitConverter.UInt32BitsToSingle(bits);
            }
            var chunk = new SourceStreamChunk(sequence, absoluteFrame, (uint)frames, logicalBlock, logicalOffset, count, samples);
            pcmHash.AppendData(record.Payload);
            sequence = checked(sequence + 1); absoluteFrame += frames; ReceivedFrames += frames; logicalOffset += frames;
            if (logicalOffset == logicalFrames) { logicalBlock = checked(logicalBlock + 1); logicalOffset = logicalFrames = 0; }
            return chunk;
        }
        catch { failed = true; throw; }
    }

    private async Task<(ushort Kind, JsonDocument Document, byte[] Payload)> ReadRecord(CancellationToken cancellation)
    {
        var header = new byte[16];
        await ReadExactly(header, cancellation);
        Require(header.AsSpan(0, 4).SequenceEqual("RBAS"u8) && BinaryPrimitives.ReadUInt16LittleEndian(header.AsSpan(4)) == 1,
            "Unsupported source stream framing.");
        var kind = BinaryPrimitives.ReadUInt16LittleEndian(header.AsSpan(6));
        var metadataBytes = BinaryPrimitives.ReadUInt32LittleEndian(header.AsSpan(8));
        var payloadBytes = BinaryPrimitives.ReadUInt32LittleEndian(header.AsSpan(12));
        Require(kind is >= 1 and <= 4 && metadataBytes is > 0 and <= MaximumMetadataBytes &&
            payloadBytes <= MaximumPayloadBytes && (kind == 2 || payloadBytes == 0), "Invalid source record size or kind.");
        var metadata = new byte[(int)metadataBytes];
        await ReadExactly(metadata, cancellation);
        var document = JsonDocument.Parse(metadata, new JsonDocumentOptions { MaxDepth = 64 });
        try
        {
            Require(document.RootElement.ValueKind == JsonValueKind.Object, "Source metadata must be an object.");
            Unique(document.RootElement);
            var payload = new byte[(int)payloadBytes];
            await ReadExactly(payload, cancellation);
            return (kind, document, payload);
        }
        catch { document.Dispose(); throw; }
    }
    private async Task ReadExactly(Memory<byte> bytes, CancellationToken cancellation)
    {
        while (!bytes.IsEmpty)
        {
            var count = await input.ReadAsync(bytes, cancellation);
            if (count == 0) throw new EndOfStreamException("The source worker stopped without a complete terminal record.");
            bytes = bytes[count..];
        }
    }
    private void ThrowFailure(JsonElement data, string generation)
    {
        if (data.TryGetProperty("generation", out _)) Require(SameID(Text(data, "generation"), generation), "A worker failure belongs to another generation.");
        var code = Text(data, "code"); var message = Text(data, "message");
        Require(code is "startup" or "ticket" or "sourceChanged" or "preparation" or "producer" or "output" && message.Length is > 0 and <= 512,
            "Malformed source worker failure.");
        if (data.TryGetProperty("lastSequence", out _)) Require(sequence > 0 && Integer(data, "lastSequence") == sequence - 1, "Incorrect failed source sequence.");
        if (data.TryGetProperty("lastAbsoluteFrame", out _)) Require(admission is not null && Integer(data, "lastAbsoluteFrame") == absoluteFrame, "Incorrect failed source position.");
        // Do not expose untrusted child diagnostics or ticket paths in UI.
        throw new IOException("The source worker rejected playback (" + code + "). Check the source and attached media, then prepare again.");
    }
    public void Dispose() => pcmHash.Dispose();
}
