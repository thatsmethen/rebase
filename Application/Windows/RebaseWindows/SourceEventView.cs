using System.Text.Json;

namespace Rebase.Windows;

// A display projection of preserved JSON, never an editable timeline Clip.
public sealed record SourceEventView(string Id, string Name, string TrackName, string SourceSHA256, string? MediaSHA256)
{
    public string DisplayName => $"{TrackName} — {Name}";
    public string MediaStatus => MediaSHA256 is null ? "No matching media attached" : "Media attached; checked again for each audition";
    public static SourceEventView[] Read(ProjectView? project)
    {
        if (project is null) return [];
        var result = new List<SourceEventView>();
        foreach (var track in project.Tracks)
        foreach (var item in track.UnresolvedAudioEvents)
        {
            var id = Text(item, "id");
            var source = Text(item, "sourceSHA256");
            string? media = null;
            if (item.TryGetProperty("files", out var files) && files.ValueKind == JsonValueKind.Array && files.GetArrayLength() == 1 &&
                files[0].TryGetProperty("object", out var fileObject) && fileObject.TryGetProperty("identityOffset", out var identity) && identity.TryGetInt64(out var offset))
            {
                var matches = project.CprMediaAttachments.Where(attachment =>
                    Text(attachment, "association") == "user-selected" && Text(attachment, "sourceSHA256") == source &&
                    attachment.TryGetProperty("sourceFileIdentity", out var value) && value.TryGetInt64(out var saved) && saved == offset).ToArray();
                if (matches.Length == 1) media = Text(matches[0], "mediaSHA256");
            }
            result.Add(new(id, Text(item, "name"), track.Name, source, media));
        }
        return result.ToArray();
    }
    private static string Text(JsonElement element, string property) => element.ValueKind == JsonValueKind.Object &&
        element.TryGetProperty(property, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() ?? "" : "";
}
