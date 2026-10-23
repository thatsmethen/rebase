namespace Rebase.Windows;

public sealed partial class StudioViewModel
{
    private async Task<bool> EditAutomation(string trackID, ulong expectedRevision, SessionRequest request)
    {
        var succeeded = false;
        await Execute(async () =>
        {
            // This check is inside the serialized queue: a draft captured before
            // an earlier edit must not be silently rebound to its newer state.
            if (State.Revision != expectedRevision)
                throw new InvalidOperationException("The project changed. Reset the automation fields before applying this edit.");
            if (Project?.Tracks.All(track => track.Id != trackID) != false)
                throw new InvalidOperationException("The automation track is no longer available.");
            request.TrackID = trackID;
            await Send(request);
            Status = "Automation updated.";
            succeeded = true;
        });
        return succeeded;
    }
    public Task<bool> UpsertAutomationPoint(string trackID, string? pointID, double time, double value, string interpolation, ulong expectedRevision, string parameter = "gainDB") =>
        EditAutomation(trackID, expectedRevision, new() { Command = "upsertAutomationPoint", Parameter = parameter, PointID = pointID, Time = time, Value = value, Interpolation = interpolation });
    public Task<bool> RemoveAutomationPoint(string trackID, string pointID, ulong expectedRevision, string parameter = "gainDB") =>
        EditAutomation(trackID, expectedRevision, new() { Command = "removeAutomationPoint", Parameter = parameter, PointID = pointID });
    public Task<bool> SetAutomationRead(string trackID, bool enabled, ulong expectedRevision, string parameter = "gainDB") =>
        EditAutomation(trackID, expectedRevision, new() { Command = "setAutomationRead", Parameter = parameter, Enabled = enabled });
    public Task<bool> AutomationHistory(string command, string trackID, ulong expectedRevision)
    {
        if (command is not ("undo" or "redo")) throw new ArgumentException("Automation history accepts only undo or redo.", nameof(command));
        return EditAutomation(trackID, expectedRevision, new() { Command = command });
    }
}
