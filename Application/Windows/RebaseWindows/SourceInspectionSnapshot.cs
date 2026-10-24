namespace Rebase.Windows;

public sealed class SourceInspectionSnapshot
{
    public ulong Revision { get; set; }
    public string EventID { get; set; } = "";
    public string SourceSHA256 { get; set; } = "";
    public string AvailabilityScope { get; set; } = "";
    public ulong MaximumFrames { get; set; }
    public SourceModeAvailability[] Modes { get; set; } = [];

    public void Validate(ulong revision, SourceEventView source)
    {
        if (AvailabilityScope != "preparation-only" || MaximumFrames != 32_000_000 ||
            Revision != revision || !string.Equals(EventID, source.Id, StringComparison.OrdinalIgnoreCase) ||
            !string.Equals(SourceSHA256, source.SourceSHA256, StringComparison.OrdinalIgnoreCase) ||
            Modes.Length != SourceAuditionMode.All.Length || Modes.Select(m => m.Mode).Distinct().Count() != Modes.Length)
            throw new InvalidDataException("The source inspection does not belong to the selected event and revision.");
        foreach (var item in Modes)
        {
            _ = SourceAuditionMode.Find(item.Mode);
            if (item.Available)
            {
                if (item.Reason is not null || item.SampleRate is not { } rate || !double.IsFinite(rate) ||
                    rate < 8000 || rate > 192000 || rate != Math.Truncate(rate) ||
                    item.Frames is not { } frames || frames == 0 || frames > 32_000_000 ||
                    item.SourceSampleRate is not { } sourceRate || !double.IsFinite(sourceRate) ||
                    sourceRate < 8000 || sourceRate > 192000 || sourceRate != Math.Truncate(sourceRate) ||
                    source.MediaSHA256 is null || !string.Equals(item.MediaSHA256, source.MediaSHA256, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("The source inspection contains inconsistent playback metadata.");
            }
            else if (string.IsNullOrWhiteSpace(item.Reason) || item.Reason.Length > 16_384)
                throw new InvalidDataException("An unavailable source mode omitted its reason.");
        }
    }
}

public sealed class SourceModeAvailability
{
    public string Mode { get; set; } = "";
    public bool Available { get; set; }
    public string? Reason { get; set; }
    public double? SampleRate { get; set; }
    public ulong? Frames { get; set; }
    public double? SourceSampleRate { get; set; }
    public string? MediaSHA256 { get; set; }
    public int? ContributorCount { get; set; }
    public int? FragmentCount { get; set; }
}
