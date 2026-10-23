using System.Text.Json;
using System.Text.Json.Serialization;

namespace Rebase.Windows;

// A validated read-only view of the original extension data. No serialized
// project or lane is constructed by the host; edits always go to Swift.
public sealed record AutomationPointView(
    [property: JsonRequired] string Id,
    [property: JsonRequired] double Time,
    [property: JsonRequired] double Value,
    [property: JsonRequired] string Interpolation)
{
    public string Display => $"{Time:0.######} s   {Value:0.###}   {(Interpolation == "step" ? "Hold" : "Linear")}";
}
public sealed record AutomationLaneView(string Id, bool IsReadEnabled, IReadOnlyList<AutomationPointView> Points)
{
    public static AutomationLaneView? ReadVolume(TrackView track) => Read(track, "gainDB");
    public static AutomationLaneView? Read(TrackView track, string parameterName)
    {
        if (parameterName is not ("gainDB" or "pan")) throw new ArgumentException("Unsupported automation parameter.", nameof(parameterName));
        var minimum = parameterName == "gainDB" ? -96 : -1;
        var maximum = parameterName == "gainDB" ? 24 : 1;
        if (track.AdditionalFields is null || !track.AdditionalFields.TryGetValue("automation", out var raw)) return null;
        if (raw.ValueKind != JsonValueKind.Array) throw new InvalidDataException("Track automation must be an array.");
        AutomationLaneView? volume = null;
        try
        {
            foreach (var lane in raw.EnumerateArray())
            {
                if (lane.ValueKind != JsonValueKind.Object || !lane.TryGetProperty("parameter", out var parameter) || parameter.ValueKind != JsonValueKind.String)
                    throw new InvalidDataException("The automation lane is malformed.");
                if (parameter.GetString() != parameterName) continue;
                if (volume is not null) throw new InvalidDataException("More than one automation lane for this parameter was returned.");
                var id = lane.GetProperty("id").GetString();
                var enabled = lane.GetProperty("isReadEnabled").GetBoolean();
                var points = lane.GetProperty("points").Deserialize<AutomationPointView[]>(ProtocolJson.Options)
                    ?? throw new InvalidDataException("The automation points are missing.");
                if (!Guid.TryParse(id, out _)) throw new InvalidDataException("The automation lane identifier is invalid.");
                var seen = new HashSet<Guid>(); var previous = -1d;
                foreach (var point in points)
                {
                    if (point is null || !Guid.TryParse(point.Id, out var pointID) || !seen.Add(pointID) ||
                        !double.IsFinite(point.Time) || point.Time < 0 || point.Time > 86400 || point.Time <= previous ||
                        !double.IsFinite(point.Value) || point.Value < minimum || point.Value > maximum || point.Interpolation is not ("linear" or "step"))
                        throw new InvalidDataException("Automation needs unique increasing times, valid identifiers, values within the parameter range, and Linear or Hold segments.");
                    previous = point.Time;
                }
                volume = new(id!, enabled, Array.AsReadOnly(points));
            }
            return volume;
        }
        catch (Exception error) when (error is JsonException or InvalidOperationException or KeyNotFoundException)
        { throw new InvalidDataException("The automation projection is malformed.", error); }
    }
}
