using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Rebase.Windows;

public sealed class ProjectStructurePage
{
    public const int ChunkBytes = 65536, MaximumReportBytes = 8 * 1024 * 1024;
    [JsonRequired] public string ReviewID { get; set; } = "";
    [JsonRequired] public ulong Revision { get; set; }
    [JsonRequired] public string ProjectID { get; set; } = "";
    [JsonRequired] public string ProjectManifestSHA256 { get; set; } = "";
    [JsonRequired] public string SourceSHA256 { get; set; } = "";
    [JsonRequired] public int SourceByteCount { get; set; }
    [JsonRequired] public string ReportSHA256 { get; set; } = "";
    [JsonRequired] public int ReportByteCount { get; set; }
    [JsonRequired] public int Offset { get; set; }
    public int? NextOffset { get; set; }
    [JsonRequired] public string BytesBase64 { get; set; } = "";

    internal static bool Digest(string? value) => value is { Length: 64 } && value.All(char.IsAsciiHexDigit);
    internal static bool Identity(string? value) => Guid.TryParseExact(value, "D", out _);
    internal static bool SameID(string? left, string? right) => Identity(left) && Identity(right) && Guid.Parse(left!) == Guid.Parse(right!);
    internal static bool SameHash(string? left, string? right) => Digest(left) && Digest(right) && string.Equals(left, right, StringComparison.OrdinalIgnoreCase);
    public byte[] Validate(int? expectedOffset = null)
    {
        if (!Identity(ReviewID) || !Identity(ProjectID) || !Digest(ProjectManifestSHA256) || !Digest(SourceSHA256) || !Digest(ReportSHA256) ||
            SourceByteCount <= 0 || ReportByteCount is < 1 or > MaximumReportBytes || Offset < 0 || Offset >= ReportByteCount || Offset % ChunkBytes != 0 ||
            expectedOffset is { } offset && Offset != offset || BytesBase64 is null || BytesBase64.Length > 4 * ((ChunkBytes + 2) / 3))
            throw new InvalidDataException("The saved structure page has invalid identity, bounds or source metadata.");
        var count = Math.Min(ChunkBytes, ReportByteCount - Offset);
        if (NextOffset != (Offset + count < ReportByteCount ? Offset + count : (int?)null))
            throw new InvalidDataException("The saved structure page does not advance exactly to the next byte boundary.");
        byte[] bytes;
        try { bytes = Convert.FromBase64String(BytesBase64); }
        catch (FormatException error) { throw new InvalidDataException("The saved structure page is not valid Base64.", error); }
        if (bytes.Length != count || Convert.ToBase64String(bytes) != BytesBase64)
            throw new InvalidDataException("The saved structure page is incomplete or uses noncanonical Base64.");
        return bytes;
    }
    public void ValidateContinuation(ProjectStructurePage first, int offset)
    {
        _ = Validate(offset);
        if (!SameID(ReviewID, first.ReviewID) || Revision != first.Revision || !SameID(ProjectID, first.ProjectID) ||
            !SameHash(ProjectManifestSHA256, first.ProjectManifestSHA256) || !SameHash(SourceSHA256, first.SourceSHA256) ||
            SourceByteCount != first.SourceByteCount || !SameHash(ReportSHA256, first.ReportSHA256) || ReportByteCount != first.ReportByteCount)
            throw new InvalidDataException("The saved structure changed between pages. Inspect it again.");
    }
}

/// Complete immutable report; raw saved numbers are deliberately never converted
/// into application gain, pan or an effective route.
public sealed class ProjectStructureSnapshot
{
    public string Json { get; }
    public string SourceSHA256 { get; }
    public string ReportSHA256 { get; }
    public string ProjectManifestSHA256 { get; }
    public string ProjectID { get; }
    public ulong Revision { get; }
    public int SourceByteCount { get; }
    public int ReportByteCount { get; }
    public IReadOnlyList<string> Hierarchy { get; }
    public IReadOnlyList<string> Tracks { get; }
    public IReadOnlyList<string> Issues { get; }
    public int ListCount { get; }
    public int ObjectCount { get; }
    public int ResourceAssociationCount { get; }
    public const string Scope = "Preserved source only; later project edits are not represented. Saved Volume and bus values are raw candidates, not application gain or effective routing. Runtime processing remains unresolved.";

    private ProjectStructureSnapshot(ProjectStructurePage page, string json, JsonElement report)
    {
        Json = json; SourceSHA256 = page.SourceSHA256; ReportSHA256 = page.ReportSHA256;
        ProjectManifestSHA256 = page.ProjectManifestSHA256; ProjectID = page.ProjectID; Revision = page.Revision;
        SourceByteCount = page.SourceByteCount; ReportByteCount = page.ReportByteCount;
        ListCount = report.GetProperty("lists").GetArrayLength(); ObjectCount = report.GetProperty("nativeObjects").GetArrayLength();
        ResourceAssociationCount = report.GetProperty("resourceAssociations").GetArrayLength();
        Hierarchy = System.Array.AsReadOnly(report.GetProperty("entries").EnumerateArray().Select(e =>
            $"{string.Join(" / ", e.GetProperty("path").EnumerateArray().Select(v => v.GetInt32()))} · {e.GetProperty("role").GetString()} · " +
            (e.TryGetProperty("object", out var obj) && obj.ValueKind != JsonValueKind.Null ? ObjectLabel(obj) : "No resolved object") +
            (e.GetProperty("repeatedIdentity").GetBoolean() ? " · repeated identity" : "")).ToArray());
        Tracks = System.Array.AsReadOnly(report.GetProperty("tracks").EnumerateArray().Select(t =>
            $"{ObjectLabel(t.GetProperty("track"))}\nProvider: {OptionalText(t, "providerName")} · index {OptionalRaw(t, "providerIndex")}\n" +
            $"State: {t.GetProperty("stateRepresentation").GetString()} · extent {(t.GetProperty("stateExtentKnown").GetBoolean() ? "bounded" : "unresolved")}\n" +
            $"Saved Volume: {NumberLabel(t, "volumeValue")} · Output selector: {NumberLabel(t, "outputBusValue")}\n" +
            $"Bus candidates: {t.GetProperty("busCandidates").GetArrayLength()} · destination candidates: {t.GetProperty("savedDestinationCandidates").GetArrayLength()}\n" +
            string.Join(" · ", t.GetProperty("unresolved").EnumerateArray().Select(v => v.GetString()))).ToArray());
        Issues = System.Array.AsReadOnly(report.GetProperty("issues").EnumerateArray().Select(i =>
            $"{i.GetProperty("code").GetString()} · {i.GetProperty("detail").GetString()}\nSource byte {i.GetProperty("span").GetProperty("offset").GetInt32()}").ToArray());
    }
    private static string ObjectLabel(JsonElement obj) => $"{obj.GetProperty("className").GetString()} · identity {obj.GetProperty("identityOffset").GetInt32()}";
    private static string OptionalText(JsonElement obj, string key) => obj.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString()! : "unresolved";
    private static string OptionalRaw(JsonElement obj, string key) => obj.TryGetProperty(key, out var v) && v.ValueKind != JsonValueKind.Null ? v.GetRawText() : "unresolved";
    private static string NumberLabel(JsonElement obj, string key) => obj.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.Object ?
        v.GetProperty("encoding").GetString() + " " + (v.TryGetProperty("integer", out var integer) ? integer.GetString() : OptionalText(v, "floatingPointBits")) : "unresolved";

    public static ProjectStructureSnapshot Decode(ProjectStructurePage first, byte[] bytes)
    {
        _ = first.Validate(0);
        if (bytes.Length != first.ReportByteCount || !ProjectStructurePage.SameHash(Convert.ToHexString(SHA256.HashData(bytes)), first.ReportSHA256))
            throw new InvalidDataException("The complete saved structure does not match its declared hash and length.");
        string json;
        try { json = new UTF8Encoding(false, true).GetString(bytes); }
        catch (DecoderFallbackException error) { throw new InvalidDataException("The saved structure is not complete UTF-8.", error); }
        using var document = JsonDocument.Parse(json, new() { MaxDepth = 64 });
        var root = document.RootElement;
        Unique(root);
        if (Int(root, "schemaVersion") != 1 || Text(root, "sourceSHA256") != first.SourceSHA256 || Int(root, "sourceByteCount") != first.SourceByteCount)
            throw new InvalidDataException("The saved structure schema or preserved source identity does not match.");
        var section = Field(root, "section", JsonValueKind.Object);
        _ = Text(section, "name"); _ = Text(section, "className");
        Position(section, "rootOffset", first.SourceByteCount); Range(section, "archiveOffset", "archiveByteCount", "archiveSHA256", first.SourceByteCount);
        foreach (var key in new[] { "arrangement", "root", "rootList" }) Object(Field(root, key, JsonValueKind.Object), first.SourceByteCount);
        foreach (var value in Array(root, "nativeObjects")) Object(value, first.SourceByteCount);
        foreach (var value in Array(root, "lists"))
        {
            Object(Field(value, "object", JsonValueKind.Object), first.SourceByteCount); _ = Text(value, "name"); _ = Int(value, "datumKind"); Nonnegative(value, "childCount");
            OptionalString(value, "scalarBits"); OptionalInt(value, "compatibilityWord", 0, ushort.MaxValue);
            foreach (var timing in Array(value, "timingObjects")) if (timing.ValueKind != JsonValueKind.Null) Object(timing, first.SourceByteCount);
        }
        foreach (var value in Array(root, "entries"))
        {
            var path = Array(value, "path"); if (path.Length == 0 || path.Any(p => !p.TryGetInt32(out var n) || n < 0)) throw new InvalidDataException("Invalid counted hierarchy path.");
            Position(value, "parentListIdentity", first.SourceByteCount); Span(Field(value, "token", JsonValueKind.Object), first.SourceByteCount);
            OptionalObject(value, "object", first.SourceByteCount); _ = Bool(value, "repeatedIdentity"); _ = Text(value, "role");
        }
        foreach (var value in Array(root, "tracks"))
        {
            Object(Field(value, "track", JsonValueKind.Object), first.SourceByteCount); OptionalObject(value, "resource", first.SourceByteCount); OptionalObject(value, "retainedObject", first.SourceByteCount);
            OptionalInt(value, "mTrackVersion"); OptionalInt(value, "providerIndex");
            foreach (var key in new[] { "tag", "retainedObjectWord", "audioFlags" }) OptionalInt(value, key, 0, ushort.MaxValue);
            OptionalString(value, "providerName"); OptionalString(value, "secondaryName");
            _ = Text(value, "stateRepresentation"); _ = Bool(value, "stateExtentKnown");
            if (value.TryGetProperty("state", out var span) && span.ValueKind != JsonValueKind.Null) Span(span, first.SourceByteCount);
            Number(value, "outputBusValue", first.SourceByteCount); Number(value, "volumeValue", first.SourceByteCount);
            foreach (var bus in Array(value, "busCandidates")) Bus(bus, first.SourceByteCount);
            foreach (var destination in Array(value, "savedDestinationCandidates")) Span(destination, first.SourceByteCount);
            foreach (var issue in Array(value, "unresolved")) if (issue.ValueKind != JsonValueKind.String) throw new InvalidDataException("Invalid unresolved track condition.");
        }
        foreach (var value in Array(root, "resourceAssociations"))
        {
            Object(Field(value, "track", JsonValueKind.Object), first.SourceByteCount); OptionalObject(value, "resource", first.SourceByteCount);
            Span(Field(value, "prefix", JsonValueKind.Object), first.SourceByteCount); Span(Field(value, "remainingTail", JsonValueKind.Object), first.SourceByteCount); _ = Text(value, "scope");
        }
        foreach (var value in Array(root, "issues"))
        { _ = Text(value, "code"); _ = Text(value, "detail"); OptionalInt(value, "objectIdentity", 0, first.SourceByteCount); Span(Field(value, "span", JsonValueKind.Object), first.SourceByteCount); }
        return new(first, json, root);
    }
    private static void Unique(JsonElement v)
    {
        if (v.ValueKind == JsonValueKind.Object)
        {
            var keys = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var p in v.EnumerateObject()) { if (!keys.Add(p.Name)) throw new InvalidDataException("Duplicate saved structure field."); Unique(p.Value); }
        }
        else if (v.ValueKind == JsonValueKind.Array) foreach (var child in v.EnumerateArray()) Unique(child);
    }
    private static JsonElement Field(JsonElement obj, string key, JsonValueKind kind) => obj.ValueKind == JsonValueKind.Object && obj.TryGetProperty(key, out var v) && v.ValueKind == kind ? v : throw new InvalidDataException("Missing or invalid saved structure field: " + key);
    private static string Text(JsonElement obj, string key) => Field(obj, key, JsonValueKind.String).GetString()!;
    private static int Int(JsonElement obj, string key) => Field(obj, key, JsonValueKind.Number).TryGetInt32(out var v) ? v : throw new InvalidDataException("Invalid saved structure integer: " + key);
    private static bool Bool(JsonElement obj, string key) => obj.TryGetProperty(key, out var v) && v.ValueKind is JsonValueKind.True or JsonValueKind.False ? v.GetBoolean() : throw new InvalidDataException("Invalid saved structure flag: " + key);
    private static JsonElement[] Array(JsonElement obj, string key) => Field(obj, key, JsonValueKind.Array).EnumerateArray().ToArray();
    private static void Nonnegative(JsonElement obj, string key) { if (Int(obj, key) < 0) throw new InvalidDataException("Negative saved structure count."); }
    private static void Position(JsonElement obj, string key, int count) { var n = Int(obj, key); if (n < 0 || n > count) throw new InvalidDataException("Saved structure offset is outside the source."); }
    private static void Range(JsonElement obj, string offset, string length, string hash, int count)
    { var start = Int(obj, offset); var size = Int(obj, length); if (start < 0 || size < 0 || (long)start + size > count || !ProjectStructurePage.Digest(Text(obj, hash))) throw new InvalidDataException("Saved structure range is outside the source or lacks a hash."); }
    private static void Span(JsonElement obj, int count) => Range(obj, "offset", "byteCount", "sha256", count);
    private static void Object(JsonElement obj, int count)
    {
        _ = Text(obj, "className"); _ = Int(obj, "version");
        foreach (var key in new[] { "declarationOffset", "objectOffset", "identityOffset" }) Position(obj, key, count);
        Range(obj, "payloadOffset", "payloadByteCount", "payloadSHA256", count);
    }
    private static void OptionalObject(JsonElement obj, string key, int count) { if (obj.TryGetProperty(key, out var v) && v.ValueKind != JsonValueKind.Null) Object(v, count); }
    private static void OptionalString(JsonElement obj, string key)
    { if (obj.TryGetProperty(key, out var v) && v.ValueKind is not (JsonValueKind.Null or JsonValueKind.String)) throw new InvalidDataException("Invalid saved structure text: " + key); }
    private static void OptionalInt(JsonElement obj, string key, int minimum = int.MinValue, int maximum = int.MaxValue)
    { if (obj.TryGetProperty(key, out var v) && v.ValueKind != JsonValueKind.Null && (v.ValueKind != JsonValueKind.Number || !v.TryGetInt32(out var n) || n < minimum || n > maximum)) throw new InvalidDataException("Invalid saved structure integer: " + key); }
    private static void Number(JsonElement obj, string key, int count)
    {
        if (!obj.TryGetProperty(key, out var n) || n.ValueKind == JsonValueKind.Null) return;
        var encoding = Text(n, "encoding"); var finite = Bool(n, "finite"); Span(Field(n, "span", JsonValueKind.Object), count);
        var integer = n.TryGetProperty("integer", out var i) && i.ValueKind == JsonValueKind.String;
        var bits = n.TryGetProperty("floatingPointBits", out var b) && b.ValueKind == JsonValueKind.String;
        if (integer == bits) throw new InvalidDataException("Saved numeric representation is ambiguous or missing.");
        if (integer)
        {
            if (encoding is not ("signed32-in-int64" or "int64-outside-signed32") || !finite ||
                !long.TryParse(i.GetString(), System.Globalization.NumberStyles.AllowLeadingSign, System.Globalization.CultureInfo.InvariantCulture, out var value) ||
                (encoding == "signed32-in-int64") != (value >= int.MinValue && value <= int.MaxValue))
                throw new InvalidDataException("Invalid saved integer representation.");
        }
        else
        {
            var text = b.GetString()!;
            if (encoding != "float64" || text.Length != 16 || !text.All(char.IsAsciiHexDigit) ||
                !ulong.TryParse(text, System.Globalization.NumberStyles.HexNumber, System.Globalization.CultureInfo.InvariantCulture, out var raw) ||
                double.IsFinite(BitConverter.UInt64BitsToDouble(raw)) != finite)
                throw new InvalidDataException("Invalid saved floating-point representation.");
        }
    }
    private static void Bus(JsonElement obj, int count)
    {
        foreach (var item in Array(obj, "path")) if (item.ValueKind != JsonValueKind.String) throw new InvalidDataException("Invalid saved bus path.");
        Span(Field(obj, "span", JsonValueKind.Object), count); _ = Text(obj, "scope"); OptionalString(obj, "name"); Number(obj, "savedUID", count); Number(obj, "busType", count);
        foreach (var child in Array(obj, "children")) Bus(child, count);
    }
}
