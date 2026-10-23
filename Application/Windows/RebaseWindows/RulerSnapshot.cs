using System.Globalization;

namespace Rebase.Windows;

public sealed class RulerSnapshot
{
    public ulong Revision { get; set; }
    public double Duration { get; set; }
    public double PixelsPerSecond { get; set; }
    public RulerTick[] Ticks { get; set; } = [];
    public void Validate(RulerRequest request)
    {
        if (Revision != request.Revision || !double.IsFinite(Duration) || Duration != request.Duration || Duration < 0 || Duration > 86400 ||
            !double.IsFinite(PixelsPerSecond) || PixelsPerSecond != request.PixelsPerSecond || PixelsPerSecond < 4 || PixelsPerSecond > 420 ||
            Ticks is null || Ticks.Length is < 1 or > 8192)
            throw new InvalidDataException("The musical ruler does not match this project view.");
        double previousTime = -1; ulong previousLabel = 0;
        foreach (var tick in Ticks)
        {
            if (tick is null || !double.IsFinite(tick.Seconds) || tick.Seconds < 0 || tick.Seconds > Duration || tick.Seconds <= previousTime ||
                tick.Label is null || tick.Label.Length is < 1 or > 10 || !tick.Label.All(char.IsAsciiDigit) ||
                !ulong.TryParse(tick.Label, NumberStyles.None, CultureInfo.InvariantCulture, out var label) || label < 1 || label < previousLabel)
                throw new InvalidDataException("The musical ruler contains invalid or unordered ticks.");
            previousTime = tick.Seconds; previousLabel = label;
        }
        if (Ticks[0].Seconds != 0 || !Ticks[0].Bar || Ticks[0].Label != "1")
            throw new InvalidDataException("The musical ruler has no valid project origin.");
    }
}
public sealed class RulerTick
{
    public double Seconds { get; set; }
    public bool Bar { get; set; }
    public string Label { get; set; } = "";
}
public sealed record RulerRequest(ulong Revision, double Duration, double PixelsPerSecond);
