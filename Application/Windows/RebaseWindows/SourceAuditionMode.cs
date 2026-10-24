namespace Rebase.Windows;

// These names are protocol values shared with CPRSourceEventPlaybackMode.
// Output-device conversion is a separate downstream operation.
public sealed record SourceAuditionMode(string Id, string Name, string Description, bool UsesTimeline)
{
    public const string Original = "sourceRate";
    public const string CompleteTrack = "nativeTrackSavedProjectClock";
    public static readonly SourceAuditionMode[] All =
    [
        new(Original, "Original source rate", "Plays the complete attached source with its saved event gain. Position is event-local; project mixer, effects and automation are bypassed.", false),
        new("nativeTimelineSourceRate", "Timeline · source rate", "Uses the saved event start, trim and offset with the preserved source clock. Reads at the source rate; project tempo edits do not alter this audition.", true),
        new("nativeTimelineProjectClock", "Timeline · current project rate", "Reads source frames at the current Rebase project rate without conversion. Different source and playback rates change speed and pitch. Saved event placement is preserved.", true),
        new("nativeTimelineSavedProjectClock", "Timeline · saved project rate", "Uses the rate explicitly saved in the original CPR, independently of Rebase rate and tempo edits. Frames remain unconverted, so different rates change speed and pitch.", true),
        new(CompleteTrack, "Complete track · saved project rate", "Checks every original contributor and attachment, including covered events. Saved priorities and source order select audible fragments at the saved project rate. Routing, mixer and effects are bypassed.", true),
        new("nativeMode0ProjectRate", "Project rate · linear mode 0", "Converts the complete event with the reconstructed mode 0 operation, then applies its saved gain and output stage. Seeking reconstructs conversion state from the start.", false),
        new("nativeMode1ProjectRate", "Project rate · sinc mode 1", "Converts the complete event with the reconstructed mode 1 filter, then applies its saved gain and output stage. Reference sample equivalence remains unverified.", false),
        new("nativeMode2ProjectRate", "Project rate · SoXR mode 2", "Uses the reconstructed mode 2 wrapper with public SoXR 0.1.3. This explicit source conversion is separate from device-rate conversion. Reference sample equivalence remains unverified.", false)
    ];
    public static SourceAuditionMode Find(string id) => All.FirstOrDefault(m => m.Id == id)
        ?? throw new InvalidDataException("Unknown source audition mode.");
}
