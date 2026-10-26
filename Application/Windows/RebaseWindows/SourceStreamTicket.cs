using System.Text.Json;

namespace Rebase.Windows;

public sealed class SourceStreamTicket
{
    public required string Generation { get; init; }
    public required ulong Revision { get; init; }
    public required string EventID { get; init; }
    public required string Mode { get; init; }
    public required string TicketPath { get; init; }
    public required string TicketSHA256 { get; init; }
    public required string Capability { get; init; }
    public required string ProofSHA256 { get; init; }
    public required uint SampleRate { get; init; }
    public required ulong StartFrame { get; init; }
    public required ulong TotalFrames { get; init; }
    public required ulong Frames { get; init; }
    public required uint MaximumChunkFrames { get; init; }

    public void Validate(string path, ulong revision, SourceEventView selected, string mode)
    {
        _ = SourceAuditionMode.Find(mode);
        SourceStreamWire.Require(Guid.TryParse(Generation, out var generation) && generation != Guid.Empty &&
            Guid.TryParse(Capability, out var capability) && capability != Guid.Empty && generation != capability &&
            Revision == revision && SourceStreamWire.SameID(EventID, selected.Id) && Mode == mode &&
            Path.GetFullPath(TicketPath).Equals(Path.GetFullPath(path), StringComparison.OrdinalIgnoreCase) &&
            SourceStreamWire.Digest(TicketSHA256) && SourceStreamWire.Digest(ProofSHA256) && MaximumChunkFrames == 65536,
            "The source stream ticket does not match this preparation request.");
        SourceStreamWire.Interval(SampleRate, StartFrame, TotalFrames, Frames);
    }
}

public sealed record SourceStreamAdmission(SourceStreamTicket Ticket, uint MaximumChunkFrames, JsonElement Proof);
public sealed record SourceStreamChunk(ulong Sequence, ulong AbsoluteFrame, uint Frames,
    ulong LogicalBlock, ulong LogicalOffset, ulong LogicalFrames, float[] Samples);

internal static class SourceStreamWire
{
    internal const int MaximumMetadataBytes = 8 * 1024 * 1024;
    internal const int MaximumPayloadBytes = 65536 * 8;
    internal static bool Digest(string? value) => value is { Length: 64 } && value.All(c => char.IsAsciiDigit(c) || c is >= 'a' and <= 'f');
    internal static bool SameID(string? a, string? b) => Guid.TryParse(a, out var first) && Guid.TryParse(b, out var second) && first == second;
    internal static void Require(bool condition, string message)
    { if (!condition) throw new InvalidDataException(message); }
    internal static void Interval(uint rate, ulong start, ulong total, ulong frames)
    {
        Require(rate is >= 8000 and <= 192000 && total > 0 && total <= (ulong)rate * 86400 &&
            start <= total && frames == total - start, "The source stream has an invalid playback interval.");
    }
    internal static JsonElement Property(JsonElement e, string key)
    {
        Require(e.ValueKind == JsonValueKind.Object && e.TryGetProperty(key, out _), "The source stream omitted " + key + ".");
        return e.GetProperty(key);
    }
    internal static string Text(JsonElement e, string key)
    {
        var value = Property(e, key);
        Require(value.ValueKind == JsonValueKind.String, "Invalid source stream text.");
        return value.GetString()!;
    }
    internal static ulong Integer(JsonElement e, string key)
    {
        var value = Property(e, key);
        Require(value.ValueKind == JsonValueKind.Number && value.TryGetUInt64(out _), "Invalid source stream integer.");
        return value.GetUInt64();
    }
    internal static void Unique(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var p in value.EnumerateObject()) { Require(names.Add(p.Name), "Duplicate source stream field."); Unique(p.Value); }
        }
        else if (value.ValueKind == JsonValueKind.Array) foreach (var item in value.EnumerateArray()) Unique(item);
    }
}
