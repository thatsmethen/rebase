using System.Text.Json;
using System.Text.Json.Serialization;

namespace Rebase.Windows;

public sealed class SessionRequest
{
    [JsonPropertyName("protocol")] public int Protocol { get; set; } = 1;
    public ulong Id { get; set; }
    public required string Command { get; set; }
    public ulong? ExpectedRevision { get; set; }
    public string? Path { get; set; }
    public string[]? Paths { get; set; }
    public string? ClipID { get; set; }
    public string? TrackID { get; set; }
    public double? Value { get; set; }
    public double? Duration { get; set; }
    public string? Snap { get; set; }
    public bool? DiscardChanges { get; set; }
    public bool? AsCopy { get; set; }
    public string? ReviewID { get; set; }
    public string? SourceSHA256 { get; set; }
    public bool? AllowPartial { get; set; }
    public int? ReviewOffset { get; set; }
    public string? Parameter { get; set; }
    public string? PointID { get; set; }
    public double? Time { get; set; }
    public string? Interpolation { get; set; }
    public bool? Enabled { get; set; }
    public string? Mode { get; set; }
    public double? StartSeconds { get; set; }
    public bool? RewindAtEnd { get; set; }
}
public sealed class SessionResponse
{
    [JsonPropertyName("protocol")] public int Protocol { get; set; }
    public ulong Id { get; set; }
    public bool Ok { get; set; }
    public SessionState? State { get; set; }
    public RenderSnapshot? Render { get; set; }
    public WaveformSnapshot? Waveform { get; set; }
    public RulerSnapshot? Ruler { get; set; }
    public CPRReviewSnapshot? CprReview { get; set; }
    public ProjectStructurePage? ProjectStructure { get; set; }
    public SourceInspectionSnapshot? SourceInspection { get; set; }
    public SourceStreamTicket? SourceStream { get; set; }
    public SessionError? Error { get; set; }
}
public sealed class SessionError { public string Code { get; set; } = "error"; public string Message { get; set; } = "The session request failed."; }
public sealed class SessionState
{
    public ulong Revision { get; set; }
    public bool Dirty { get; set; }
    public bool NeedsSaveAs { get; set; }
    public string? Path { get; set; }
    public ProjectView? Project { get; set; }
    public SelectionView Selection { get; set; } = new();
    public bool CanUndo { get; set; }
    public bool CanRedo { get; set; }
}
public sealed class SelectionView { public string? TrackID { get; set; } public string? ClipID { get; set; } }
// Read-only projections. Only the Swift helper may produce project mutations.
public sealed class ProjectView
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public double SampleRate { get; set; }
    public double Tempo { get; set; }
    public TrackView[] Tracks { get; set; } = [];
    public JsonElement TempoMap { get; set; }
    public JsonElement SignatureMap { get; set; }
    public JsonElement[] CprMediaAttachments { get; set; } = [];
    [JsonExtensionData] public Dictionary<string, JsonElement>? AdditionalFields { get; set; }
    public double Duration => Tracks.SelectMany(t => t.Clips).Select(c => c.Position + c.Duration).DefaultIfEmpty(0).Max();
}
public sealed class TrackView
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public double GainDB { get; set; }
    public double Pan { get; set; }
    public bool IsMuted { get; set; }
    public bool IsSolo { get; set; }
    public ClipView[] Clips { get; set; } = [];
    public JsonElement[] UnresolvedAudioEvents { get; set; } = [];
    [JsonExtensionData] public Dictionary<string, JsonElement>? AdditionalFields { get; set; }
}
public sealed class ClipView
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public double Position { get; set; }
    public double Duration { get; set; }
    public double SourceOffset { get; set; }
    public string MediaPath { get; set; } = "";
    [JsonExtensionData] public Dictionary<string, JsonElement>? AdditionalFields { get; set; }
}
public sealed class RenderSnapshot
{
    public string? Kind { get; set; }
    public string? EventID { get; set; }
    public string? SourceSHA256 { get; set; }
    public string? MediaSHA256 { get; set; }
    public string? Mode { get; set; }
    public string? ManifestPath { get; set; }
    public string? ManifestSHA256 { get; set; }
    public ulong? ManifestBytes { get; set; }
    public ulong? StartFrame { get; set; }
    public ulong? TotalFrames { get; set; }
    public string Path { get; set; } = "";
    public ulong Revision { get; set; }
    public double SampleRate { get; set; }
    public ulong Frames { get; set; }
    public uint Channels { get; set; }
    public ulong WavBytes { get; set; }
    public string Sha256 { get; set; } = "";
}
public static class ProtocolJson
{
    public static readonly JsonSerializerOptions Options = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        MaxDepth = 64
    };
    public static SessionResponse Decode(string text, ulong expectedID)
    {
        if (text.Length > 16 * 1024 * 1024) throw new InvalidDataException("The session response exceeds 16 MiB.");
        using (var document = JsonDocument.Parse(text))
        {
            if (document.RootElement.ValueKind != JsonValueKind.Object)
                throw new InvalidDataException("The session response must be a JSON object.");
            var fields = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var property in document.RootElement.EnumerateObject())
            {
                if (!fields.Add(property.Name)) throw new InvalidDataException("The session returned duplicate response fields.");
                if (string.Equals(property.Name, "cprReview", StringComparison.OrdinalIgnoreCase) &&
                    property.Value.ValueKind != JsonValueKind.Null &&
                    System.Text.Encoding.UTF8.GetByteCount(property.Value.GetRawText()) > CPRReviewSnapshot.MaximumBytes)
                    throw new InvalidDataException("The CPR review page exceeds 128 KiB.");
                if (string.Equals(property.Name, "projectStructure", StringComparison.OrdinalIgnoreCase) &&
                    property.Value.ValueKind != JsonValueKind.Null && System.Text.Encoding.UTF8.GetByteCount(property.Value.GetRawText()) > 128 * 1024)
                    throw new InvalidDataException("The saved structure page exceeds 128 KiB.");
                if (string.Equals(property.Name, "projectStructure", StringComparison.OrdinalIgnoreCase) && property.Value.ValueKind == JsonValueKind.Object)
                {
                    var pageFields = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    foreach (var field in property.Value.EnumerateObject())
                        if (!pageFields.Add(field.Name)) throw new InvalidDataException("The saved structure page contains duplicate fields.");
                }
            }
        }
        var response = JsonSerializer.Deserialize<SessionResponse>(text, Options)
            ?? throw new InvalidDataException("The session returned an empty response.");
        if (response.Protocol != 1 || response.Id != expectedID)
            throw new InvalidDataException("The session protocol or response identifier does not match.");
        if (response.Ok && response.State is null) throw new InvalidDataException("The session omitted its document state.");
        response.CprReview?.Validate();
        response.ProjectStructure?.Validate();
        return response;
    }
}
