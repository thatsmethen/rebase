namespace Rebase.Windows;

public sealed partial class StudioViewModel
{
    // Source audition may use event-local or saved-clock time. Import belongs
    // to the ordinary arrangement position retained before that context.
    public double ProjectInsertionPosition => IsSourceContext ? projectPosition : Position;

    private async Task StopForDocumentChange()
    {
        audioEpoch++;
        // Do not publish a new document/edit while an old native generation
        // may still be running. Clear ownership only after a confirmed barrier.
        if (sourceStream is not null)
        {
            await sourceStream.Cancel(); sourceStream = null;
            LastSourceStreamWorkerJoined = true;
        }
        else if (loadedRevision is not null) await audio.Stop();
        loadedRevision = null; PlaybackRateInfo = null; SourcePlaybackStatus = null;
        audioPhase = 0; PeakLeft = PeakRight = 0;
    }

    public async Task<bool> NewProject(bool discardChanges = false)
    {
        var revision = State.Revision;
        var projectID = Project?.Id;
        var succeeded = false;
        await SourceAction(async () =>
        {
            if (State.Revision != revision || Project?.Id != projectID)
                throw new InvalidOperationException("The project changed while New Project was waiting. Decide whether to save or discard the current project again.");
            RequireSaveDecision(discardChanges);
            if (NeedsSaveDecision && !discardChanges)
                throw new InvalidOperationException("Save or explicitly discard changes before creating a new project.");
            await StopForDocumentChange();
            Directory.CreateDirectory(scratch);
            var path = Path.Combine(scratch, "Untitled-" + Guid.NewGuid().ToString("N") + ".rebaseproj");
            await Send(new() { Command = "newProject", Path = path, DiscardChanges = discardChanges });
            UseProjectContext(); Position = projectPosition = 0;
            Status = "New project. Import PCM WAV audio, then use Save As to keep your work.";
            succeeded = true;
        });
        return succeeded;
    }

    public async Task<bool> ImportAudio(IEnumerable<string> paths, double? insertionSeconds = null)
    {
        // Capture caller-owned values before entering the serialized action
        // queue; the helper owns decoding, snapping, media copies and history.
        var selected = paths.ToArray();
        var position = insertionSeconds ?? ProjectInsertionPosition;
        var snap = Snap;
        var revision = State.Revision;
        var projectID = Project?.Id;
        var succeeded = false;
        await SourceAction(async () =>
        {
            if (Project is null) throw new InvalidOperationException("Create or open a project before importing audio.");
            if (State.Revision != revision || Project.Id != projectID)
                throw new InvalidOperationException("The project changed while audio import was waiting. Choose the files again for the current project.");
            if (selected.Length is < 1 or > 32 || selected.Any(string.IsNullOrWhiteSpace))
                throw new InvalidOperationException("Select from 1 to 32 PCM WAV files to import.");
            if (!double.IsFinite(position) || position < 0 || position > 86400)
                throw new InvalidOperationException("Audio insertion time must be a finite project time from 0 to 86400 seconds.");
            if (snap is not ("off" or "quarter" or "eighth" or "sixteenth" or "bar"))
                throw new InvalidOperationException("Choose an available snap setting before importing audio.");
            await StopForDocumentChange();
            await Send(new() { Command = "importAudio", Paths = selected, Value = position, Snap = snap });
            UseProjectContext();
            Status = selected.Length == 1 ? "Imported audio as a new track." : $"Imported {selected.Length} audio files as separate tracks. Undo removes the complete batch.";
            succeeded = true;
        });
        return succeeded;
    }
}
