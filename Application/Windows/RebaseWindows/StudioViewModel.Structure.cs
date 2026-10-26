using System.Text.Json;

namespace Rebase.Windows;

public sealed partial class StudioViewModel
{
    public async Task<ProjectStructureSnapshot?> InspectProjectStructure()
    {
        var revision = State.Revision;
        var projectID = Project?.Id;
        ProjectStructureSnapshot? result = null;
        await Execute(async () =>
        {
            if (Project is null || !ProjectStructurePage.SameID(Project.Id, projectID) || State.Revision != revision)
                throw new InvalidOperationException("The project changed while its saved structure was waiting. Inspect the current project again.");
            var originalState = JsonSerializer.Serialize(State, ProtocolJson.Options);
            string? token = null;
            Exception? failure = null;
            ProjectStructureSnapshot? candidate = null;
            async Task<SessionResponse> Read(SessionRequest request)
            {
                request.ExpectedRevision = revision;
                var reply = await session.Send(request);
                if (reply.State is null || JsonSerializer.Serialize(reply.State, ProtocolJson.Options) != originalState ||
                    JsonSerializer.Serialize(State, ProtocolJson.Options) != originalState)
                    throw new InvalidDataException("A saved structure response changed the document state. The report was not accepted.");
                if (!reply.Ok) throw new InvalidOperationException(reply.Error?.Message ?? "The saved structure request failed.");
                return reply;
            }
            try
            {
                var first = (await Read(new() { Command = "inspectProjectStructure" })).ProjectStructure ??
                    throw new InvalidDataException("The session omitted the saved structure page.");
                // Retain a syntactically valid token before validating content so
                // malformed first pages still receive one bounded close request.
                if (ProjectStructurePage.Identity(first.ReviewID)) token = first.ReviewID;
                var block = first.Validate(0);
                if (first.Revision != revision || !ProjectStructurePage.SameID(first.ProjectID, projectID))
                    throw new InvalidDataException("The saved structure belongs to another document or revision.");
                var bytes = new byte[first.ReportByteCount];
                block.CopyTo(bytes, 0);
                var next = first.NextOffset;
                while (next is { } offset)
                {
                    var page = (await Read(new() { Command = "projectStructurePage", ReviewID = token, ReviewOffset = offset })).ProjectStructure ??
                        throw new InvalidDataException("The session omitted a saved structure continuation.");
                    page.ValidateContinuation(first, offset);
                    Convert.FromBase64String(page.BytesBase64).CopyTo(bytes, offset);
                    next = page.NextOffset;
                }
                candidate = ProjectStructureSnapshot.Decode(first, bytes);
            }
            catch (Exception error) { failure = error; }
            finally
            {
                if (token is not null)
                {
                    try { await Read(new() { Command = "closeProjectStructure", ReviewID = token }); }
                    catch (Exception error)
                    {
                        failure = new IOException((failure is null ? "The saved structure was read, but closing its review was not confirmed." : failure.Message) +
                            " Review cleanup failed: " + error.Message, failure ?? error);
                    }
                }
            }
            if (failure is not null) throw failure;
            result = candidate ?? throw new InvalidDataException("The saved structure report was incomplete.");
            Status = "Showing the complete saved source structure. Current project edits are unchanged.";
        });
        return result;
    }
}
