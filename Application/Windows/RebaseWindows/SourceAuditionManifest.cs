using System.Security.Cryptography;
using System.Text.Json;

namespace Rebase.Windows;

// The helper replays source bytes and prepares every contributor. The host binds
// its complete proof to this request, selected project and exact output bytes.
public static class SourceAuditionManifest
{
    public const ulong MaximumBytes = 8_388_608;
    public const string Suffix = ".source-audition.json";
    public static void Validate(RenderSnapshot render, string wavePath, ulong revision,
        SourceEventView selected, ProjectView project, string mode)
    {
        _ = SourceAuditionMode.Find(mode);
        Require(render.Mode == mode && render.StartFrame is { } start && render.TotalFrames is { } total &&
            total is > 0 and <= 32_000_000 && start <= total && render.Frames == total - start,
            "The source render changed its mode or playback interval.");
        var path = wavePath + Suffix;
        Require(render.ManifestPath is not null && Path.GetFullPath(render.ManifestPath).Equals(Path.GetFullPath(path), StringComparison.OrdinalIgnoreCase) &&
            render.ManifestBytes is > 0 and <= MaximumBytes && Digest(render.ManifestSHA256), "The source render omitted its complete provenance manifest.");
        var file = new FileInfo(path);
        Require((file.Attributes & FileAttributes.ReparsePoint) == 0 && (ulong)file.Length == render.ManifestBytes,
            "The source provenance file size or type changed.");
        var bytes = File.ReadAllBytes(path);
        Require((ulong)bytes.Length == render.ManifestBytes && Same(Convert.ToHexString(SHA256.HashData(bytes)), render.ManifestSHA256),
            "The source provenance no longer matches its SHA-256.");
        using var document = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 64 });
        UniqueFields(document.RootElement);
        var proof = document.RootElement;
        Require(Text(proof, "schema") == "rebase.source-audition-manifest.v1" && Integer(proof, "revision") == revision &&
            Same(Text(proof, "eventID"), selected.Id) && Text(proof, "mode") == mode &&
            Same(Text(proof, "sourceSHA256"), selected.SourceSHA256) && Same(Text(proof, "mediaSHA256"), selected.MediaSHA256) &&
            Number(proof, "sampleRate") == render.SampleRate && Integer(proof, "frames") == render.Frames &&
            Integer(proof, "startFrame") == render.StartFrame && Integer(proof, "totalFrames") == render.TotalFrames &&
            Integer(proof, "channels") == 2 && Integer(proof, "maximumFrames") == 32_000_000 &&
            Text(proof, "wavFileName") == Path.GetFileName(wavePath) && Integer(proof, "wavBytes") == render.WavBytes &&
            Same(Text(proof, "wavSHA256"), render.Sha256) && Number(proof, "projectSampleRate") == project.SampleRate,
            "The source provenance does not match this event, document, interval and WAV.");
        foreach (var key in new[] { "projectManifestSHA256", "currentProjectSHA256", "importReportSHA256", "sourceSHA256", "mediaSHA256", "wavSHA256" })
            Require(Digest(Text(proof, key)), "The source provenance contains an invalid digest.");
        var sourceRate = Number(proof, "sourceSampleRate");
        Require(sourceRate is >= 8000 and <= 192000 && sourceRate == Math.Truncate(sourceRate), "Invalid source rate in audition provenance.");
        var clock = mode switch
        {
            SourceAuditionMode.Original => "source-rate",
            "nativeTimelineSourceRate" => "source-clock-unconverted",
            "nativeTimelineProjectClock" => "current-project-clock-unconverted",
            "nativeTimelineSavedProjectClock" or SourceAuditionMode.CompleteTrack => "saved-project-clock-unconverted",
            _ => "current-project-rate-converted"
        };
        Require(Text(proof, "clockRole") == clock, "The source render changed its clock interpretation.");
        if (mode is SourceAuditionMode.Original or "nativeTimelineSourceRate") Require(render.SampleRate == sourceRate, "Source-clock output changed rate.");
        if (mode is "nativeTimelineProjectClock" or "nativeMode0ProjectRate" or "nativeMode1ProjectRate" or "nativeMode2ProjectRate")
            Require(render.SampleRate == project.SampleRate, "Project-clock output changed rate.");
        if (mode == "nativeMode0ProjectRate") Require(render.SampleRate != sourceRate, "Mode 0 accepted an equal-rate source.");
        if (mode is "nativeTimelineSavedProjectClock" or SourceAuditionMode.CompleteTrack)
        {
            var setup = Property(proof, "savedProjectAudioSetup");
            Require(Text(setup, "contract") == "cpr-15.0.30.287-parrangement-audio-setup-v1" &&
                Same(Text(setup, "sourceSHA256"), selected.SourceSHA256) && Integer(setup, "factorBits") == 0x3ff0000000000000UL &&
                Integer(setup, "baseRateBits") <= uint.MaxValue &&
                BitConverter.UInt32BitsToSingle((uint)Integer(setup, "baseRateBits")) == render.SampleRate,
                "The saved output clock is not bound to the preserved source setup.");
        }
        if (project.TempoMap.ValueKind == JsonValueKind.Object && project.TempoMap.TryGetProperty("nativeClock", out var currentClock))
        {
            Require(proof.TryGetProperty("currentNativeClock", out var reportedClock) && Equivalent(currentClock, reportedClock),
                "The source provenance changed the current project clock.");
        }
        else Require(!proof.TryGetProperty("currentNativeClock", out _), "The source provenance invented a current native clock.");
        if (SourceAuditionMode.Find(mode).UsesTimeline)
        {
            var preserved = Property(proof, "preservedNativeClock");
            Require(Same(Text(preserved, "sourceSHA256"), selected.SourceSHA256), "The timeline clock belongs to a different source.");
            if (mode != SourceAuditionMode.CompleteTrack) ValidateRange(Property(proof, "timelineRange"), mode switch
            {
                "nativeTimelineSourceRate" => "cpr-15.0.30.287-direct-source-segment-v1",
                "nativeTimelineProjectClock" => "cpr-15.0.30.287-direct-project-clock-segment-v1",
                _ => "cpr-15.0.30.287-direct-saved-project-clock-segment-v1"
            });
        }
        if (mode == SourceAuditionMode.CompleteTrack) ValidateTrack(proof, selected, project);
        else Require(Text(proof, "sourceKind") == "event" && !proof.TryGetProperty("sourceTrack", out _), "An event render returned a different scope.");
    }

    private static void ValidateTrack(JsonElement proof, SourceEventView selected, ProjectView project)
    {
        Require(Text(proof, "sourceKind") == "track", "The complete-track proof omitted its scope.");
        var tracks = project.Tracks.Where(t => t.UnresolvedAudioEvents.Any(e => Same(Text(e, "id"), selected.Id))).ToArray();
        Require(tracks.Length == 1 && tracks[0].Clips.Length == 0, "Complete-track audition requires its original track without added clips.");
        var originals = tracks[0].UnresolvedAudioEvents;
        var track = Property(proof, "sourceTrack");
        Require(Text(track, "contract") == "cpr-15.0.30.287-priority-track-fresh-root-mode0-v1" && Integer(track, "freshRootMode") == 0,
            "The complete-track proof changed its normalization contract.");
        var events = Array(track, "events"); var fragments = Array(track, "fragments");
        Require(originals.Length is > 0 and <= 4096 && events.Length == originals.Length && fragments.Length is > 0 and <= 16384,
            "The complete-track proof does not cover every retained contributor.");
        var ids = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var sources = SourceEventView.Read(project);
        var byOrdinal = new Dictionary<ulong, JsonElement>();
        foreach (var item in events)
        {
            var id = Text(item, "eventID"); var ordinal = Integer(item, "sourceOrdinal");
            Require(ids.Add(id) && ordinal < (ulong)events.Length && byOrdinal.TryAdd(ordinal, item), "Duplicate or missing track contributor identity.");
            var retained = originals.Where(e => Same(Text(e, "id"), id)).ToArray();
            var source = sources.Where(s => Same(s.Id, id)).ToArray();
            Require(retained.Length == 1 && source.Length == 1 && source[0].MediaSHA256 is not null &&
                Same(source[0].SourceSHA256, selected.SourceSHA256) && Same(Text(item, "mediaSHA256"), source[0].MediaSHA256) &&
                Integer(Property(retained[0], "event"), "identityOffset") == Integer(item, "eventIdentity"),
                "A complete-track contributor no longer matches its retained event or attached media.");
            Require(Property(item, "priority").TryGetInt32(out _), "Invalid signed event priority.");
            var start = Number(item, "canonicalStart"); var end = Number(item, "canonicalEnd");
            Require(start >= 0 && end > start && end <= 86400, "Invalid original contributor interval.");
            var rate = Number(item, "sourceSampleRate");
            Require(rate is >= 8000 and <= 192000 && rate == Math.Truncate(rate), "Invalid contributor media rate.");
            if (item.TryGetProperty("range", out var range)) ValidateRange(range, "cpr-15.0.30.287-direct-saved-project-clock-segment-v1");
        }
        double previousStart = 0;
        foreach (var fragment in fragments)
        {
            var ordinal = Integer(fragment, "sourceOrdinal");
            Require(byOrdinal.TryGetValue(ordinal, out var contributor) && Same(Text(fragment, "eventID"), Text(contributor, "eventID")) &&
                Integer(fragment, "eventIdentity") == Integer(contributor, "eventIdentity"), "An audible fragment lost its original contributor.");
            var range = Property(fragment, "range"); ValidateRange(range, "cpr-15.0.30.287-direct-saved-project-clock-segment-v1");
            var start = Number(range, "position");
            // Native non-overlap is proven in quantized reader frames by the
            // shared planner. Do not add a different double-addition rule here.
            Require(start >= previousStart, "The normalized track fragments are unordered.");
            previousStart = start;
        }
        Require(Integer(track, "snappedEmptyFragmentCount") <= 16384 && ids.Contains(selected.Id), "The complete-track proof lost its anchor.");
    }

    private static void ValidateRange(JsonElement range, string expectedContract)
    {
        Require(Text(range, "contract") == expectedContract,
            "Unknown source placement contract.");
        var start = Number(range, "position"); var duration = Number(range, "duration"); var offset = Number(range, "offset");
        // Reader endpoint admission uses recovered frame quantization in the
        // shared core. A different floating addition must not narrow it here.
        Require(start is >= 0 and <= 86400 && duration is > 0 and <= 86400 && offset is >= 0 and <= 86400,
            "The source placement has invalid coordinates.");
    }
    private static bool Equivalent(JsonElement a, JsonElement b) => JsonElement.DeepEquals(a, b);
    private static void UniqueFields(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var p in element.EnumerateObject()) { Require(names.Add(p.Name), "Duplicate provenance field."); UniqueFields(p.Value); }
        }
        else if (element.ValueKind == JsonValueKind.Array) foreach (var item in element.EnumerateArray()) UniqueFields(item);
    }
    private static JsonElement Property(JsonElement e, string name)
    {
        Require(e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out _), "Missing audition provenance field: " + name);
        return e.GetProperty(name);
    }
    private static string Text(JsonElement e, string name)
    {
        var p = Property(e, name); Require(p.ValueKind == JsonValueKind.String, "Invalid audition provenance text."); return p.GetString()!;
    }
    private static ulong Integer(JsonElement e, string name)
    {
        var p = Property(e, name); Require(p.ValueKind == JsonValueKind.Number && p.TryGetUInt64(out _), "Invalid audition provenance integer."); return p.GetUInt64();
    }
    private static double Number(JsonElement e, string name)
    {
        var p = Property(e, name); Require(p.ValueKind == JsonValueKind.Number && p.TryGetDouble(out var value) && double.IsFinite(value), "Invalid audition provenance number."); return p.GetDouble();
    }
    private static JsonElement[] Array(JsonElement e, string name)
    {
        var p = Property(e, name); Require(p.ValueKind == JsonValueKind.Array, "Invalid audition contributor list."); return p.EnumerateArray().ToArray();
    }
    private static bool Same(string? a, string? b) => a is not null && b is not null && string.Equals(a, b, StringComparison.OrdinalIgnoreCase);
    private static bool Digest(string? value) => value is { Length: 64 } && value.All(char.IsAsciiHexDigit);
    private static void Require(bool condition, string message) { if (!condition) throw new InvalidDataException(message); }
}
