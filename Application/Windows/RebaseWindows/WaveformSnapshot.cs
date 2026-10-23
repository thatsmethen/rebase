namespace Rebase.Windows;

public sealed class WaveformSnapshot
{
    public ulong Revision { get; set; }
    public string ClipID { get; set; } = "";
    public double SampleRate { get; set; }
    public ulong SourceStartFrame { get; set; }
    public ulong SourceFrames { get; set; }
    public string MediaSHA256 { get; set; } = "";
    public float[] Peaks { get; set; } = [];
    public void Validate(ClipView clip, ulong revision)
    {
        if (Revision != revision || !ClipID.Equals(clip.Id, StringComparison.OrdinalIgnoreCase) ||
            !double.IsFinite(SampleRate) || SampleRate <= 0 || SourceFrames == 0 || SourceFrames > 16_000_000 ||
            MediaSHA256.Length != 64 || !MediaSHA256.All(char.IsAsciiHexDigit) ||
            Peaks.Length != (int)Math.Min(1600ul, SourceFrames) || Peaks.Any(value => !float.IsFinite(value) || value < 0))
            throw new InvalidDataException("The waveform does not identify a bounded finite source envelope for this clip.");
        var start = clip.SourceOffset * SampleRate;
        var frames = clip.Duration * SampleRate;
        if (!double.IsFinite(start) || !double.IsFinite(frames) || start < 0 || start >= ulong.MaxValue ||
            SourceStartFrame != (ulong)Math.Truncate(start) || SourceFrames > Math.Truncate(frames))
            throw new InvalidDataException("The waveform source interval does not match this clip.");
    }
}
public sealed record WaveformRange(string MediaPath, double SourceOffset, double Duration)
{
    public static WaveformRange Of(ClipView clip) => new(clip.MediaPath, clip.SourceOffset, clip.Duration);
}
