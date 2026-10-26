using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace Rebase.Windows;

public sealed partial class StudioViewModel : INotifyPropertyChanged, IAsyncDisposable
{
    private readonly ISessionClient session;
    private readonly IAudioOutput audio;
    private readonly string scratch = Path.Combine(Path.GetTempPath(), "Rebase", Guid.NewGuid().ToString("N"));
    private readonly SemaphoreSlim actions = new(1, 1);
    private ulong? loadedRevision;
    private ulong audioEpoch;
    private string? sourceEventID;
    private string sourcePlaybackMode = SourceAuditionMode.Original;
    private ulong sourceStartFrame;
    private double sourceDuration, projectPosition;
    private readonly Dictionary<string, (WaveformRange Range, WaveformSnapshot Snapshot)> waveforms = [];
    private readonly Dictionary<string, ulong> waveformFailures = [];
    private Task? waveformTask;
    private ulong waveformEpoch;
    private Task? rulerTask;
    private RulerRequest? desiredRuler, failedRuler;
    private bool polling, closing, saveConfirmationRequired;
    private uint audioPhase;
    private bool accepting = true;
    private int pendingActions;
    private TaskCompletionSource idle = CompletedIdle();
    private static TaskCompletionSource CompletedIdle() { var source = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously); source.SetResult(); return source; }
    private string status = "Open a project, or explore the included example.";
    private bool busy;
    private double position, peakLeft, peakRight;
    public StudioViewModel(ISessionClient? session = null, IAudioOutput? audio = null, ISourceStreamFactory? streamFactory = null)
    {
        this.session = session ?? new SessionProcess();
        this.audio = audio ?? new NativeAudio();
        this.streamFactory = streamFactory ?? new SourceStreamProcessFactory();
    }
    public SessionState State { get; private set; } = new();
    public AudioRateInfo? PlaybackRateInfo { get; private set; }
    public RenderSnapshot? LastSourceExport { get; private set; }
    public SourceInspectionSnapshot? SourceInspection { get; private set; }
    public RulerSnapshot? Ruler { get; private set; }
    public string? RulerError { get; private set; }
    public ProjectView? Project => State.Project;
    public TrackView? SelectedTrack => Project?.Tracks.FirstOrDefault(t => t.Id == State.Selection.TrackID);
    public ClipView? SelectedClip => Project?.Tracks.SelectMany(t => t.Clips).FirstOrDefault(c => c.Id == State.Selection.ClipID);
    public SourceEventView[] SourceEvents => SourceEventView.Read(Project);
    public SourceEventView? SelectedSourceEvent => SourceEvents.FirstOrDefault(e => e.Id == State.Selection.ClipID);
    public bool IsSourceContext => sourceEventID is not null;
    public string SourcePlaybackMode => sourcePlaybackMode;
    public string TransportContext => sourceEventID is null ? "Project timeline" :
        (sourcePlaybackMode == SourceAuditionMode.CompleteTrack ? "Source track: " : "Source event: ") +
        (SourceEvents.FirstOrDefault(e => e.Id == sourceEventID)?.Name ?? "Unavailable") +
        (SourceAuditionMode.Find(sourcePlaybackMode).UsesTimeline ? " · saved timeline seconds" : " · event-local seconds");
    public bool NeedsSaveDecision => Project is not null && (State.Dirty || saveConfirmationRequired);
    public string Title => (Project?.Name ?? "Rebase") + (NeedsSaveDecision ? " •" : "") + " — Rebase";
    public string Status { get => status; private set { status = value; Changed(); } }
    public bool Busy { get => busy; private set { busy = value; Changed(); } }
    public double Position { get => position; private set { position = value; Changed(); } }
    public double PeakLeft { get => peakLeft; private set { peakLeft = value; Changed(); } }
    public double PeakRight { get => peakRight; private set { peakRight = value; Changed(); } }
    public string Snap { get; set; } = "off";
    public bool IsPlaying => audioPhase is 2 or 7;
    public event PropertyChangedEventHandler? PropertyChanged;
    public event Action? StateChanged;
    public event Action? WaveformsChanged;
    public event Action? RulerChanged;
    public IReadOnlyDictionary<string, float[]> WaveformPeaks => waveforms.ToDictionary(item => item.Key, item => item.Value.Snapshot.Peaks);
    private void Changed([CallerMemberName] string? property = null) => PropertyChanged?.Invoke(this, new(property));
    private void SetSaveConfirmationRequired(bool value)
    {
        saveConfirmationRequired = value;
        Changed(nameof(NeedsSaveDecision)); Changed(nameof(Title));
    }
    private void RequireSaveDecision(bool discardChanges)
    {
        if (saveConfirmationRequired && !discardChanges)
            throw new InvalidOperationException("The previous save was not confirmed. Save successfully or explicitly discard changes before replacing this project.");
    }
    public void Report(Exception error) => Status = error.Message;
    private void NotifyContext() { Changed(nameof(IsSourceContext)); Changed(nameof(TransportContext)); }
    private void UseProjectContext()
    {
        var wasSource = sourceEventID is not null;
        sourceEventID = null; sourceDuration = 0; sourceStartFrame = 0;
        if (wasSource) Position = Math.Min(projectPosition, Project?.Duration ?? 0);
        NotifyContext();
    }
    private async Task InvalidateAudio()
    {
        audioEpoch++;
        if (sourceStream is not null)
        {
            // Native cancellation is a barrier. A failed barrier must remain
            // visible and retain this generation for retry/diagnostics.
            await sourceStream.Cancel(); sourceStream = null; LastSourceStreamWorkerJoined = true;
        }
        else if (loadedRevision is not null)
        {
            try { await audio.Stop(); } catch (IOException error) { Report(error); }
        }
        loadedRevision = null; PlaybackRateInfo = null; SourcePlaybackStatus = null; audioPhase = 0; PeakLeft = PeakRight = 0;
    }
    private string PlaybackFormatSuffix => PlaybackRateInfo is { } info && info.Converted == 1
        ? $" · {info.SourceRate} → {info.EndpointRate} Hz (converted)" : "";
    private static void ValidateOutputFormat(DeviceFormat format)
    {
        if (format.Float32 != 1 || format.Channels != 2 || format.SampleRate < 8000 || format.SampleRate > 192000)
            throw new InvalidOperationException("The default output must use Float32 stereo at a rate from 8000 to 192000 Hz.");
    }
    private async Task InstallSource(LoadedSnapshot source, ulong revision)
    {
        await audio.SetSource(source);
        try
        {
            // The default endpoint can change after discovery. Bind to the
            // actual installed source and endpoint, not the earlier query.
            var info = await audio.RateInfo();
            info.ValidateForSource(source);
            PlaybackRateInfo = info; loadedRevision = revision; audioPhase = 1;
        }
        catch
        {
            loadedRevision = null; PlaybackRateInfo = null; audioPhase = 0; PeakLeft = PeakRight = 0;
            try { await audio.Stop(); } catch (IOException) { }
            throw;
        }
    }
    private void ValidateStatus(AudioStatus snapshot)
    {
        if (PlaybackRateInfo is not { } info || snapshot.AbiVersion != 1 || snapshot.Reserved != 0 ||
            snapshot.SampleRate != info.SourceRate || snapshot.TotalFrames != info.SourceFrames ||
            snapshot.PositionFrames > snapshot.SubmittedFrames || snapshot.SubmittedFrames > snapshot.TotalFrames ||
            snapshot.Phase is < 1 or > 4 || snapshot.Result != 0 || snapshot.ClockReadingApproximate > 1 ||
            !float.IsFinite(snapshot.PeakLeft) || !float.IsFinite(snapshot.PeakRight))
            throw new InvalidDataException("The native transport position does not match the installed source.");
    }
    private async Task<AudioStatus> SeekLoadedSource(ulong frame)
    {
        await audio.Seek(frame);
        var current = await audio.Status();
        ValidateStatus(current);
        // A rounded source-to-endpoint seek can reach endpoint EOF before the
        // requested source frame equals source EOF. The native cursor decides.
        Position = PlaybackPosition(current);
        audioPhase = current.Phase;
        if (audioPhase != 2) PeakLeft = PeakRight = 0;
        return current;
    }
    private double PlaybackPosition(AudioStatus snapshot) =>
        (double)(snapshot.PositionFrames + (IsSourceContext ? sourceStartFrame : 0)) / snapshot.SampleRate;
    private async Task<SessionResponse> Send(SessionRequest request)
    {
        request.ExpectedRevision = State.Revision;
        var response = await session.Send(request);
        if (response.State is not null)
        {
            var revisionChanged = State.Revision != response.State.Revision;
            // The helper may already have committed an edit. Audio cleanup
            // failure must never hide its authoritative revision/dirty state.
            State = response.State;
            Exception? cancellationFailure = null;
            if (revisionChanged || sourceEventID is not null && sourceEventID != State.Selection.ClipID)
            {
                try { await InvalidateAudio(); UseProjectContext(); }
                catch (Exception error) { cancellationFailure = error; audioPhase = 5; PeakLeft = PeakRight = 0; }
            }
            if (SourceInspection is { } inspection && (inspection.Revision != State.Revision || inspection.EventID != State.Selection.ClipID))
                SourceInspection = null;
            if (response.Ok && request.Command is "open" or "importCPR" or "newProject") SetSaveConfirmationRequired(false);
            if (Ruler is not null && Ruler.Revision != State.Revision) { Ruler = null; RulerChanged?.Invoke(); }
            if (response.Ok && request.Command is "open" or "saveAs" or "importCPR" or "newProject")
            {
                waveformEpoch++; waveforms.Clear(); waveformFailures.Clear();
            }
            var clips = Project?.Tracks.SelectMany(t => t.Clips).ToDictionary(c => c.Id) ?? [];
            foreach (var id in waveforms.Keys.Where(id => !clips.TryGetValue(id, out var clip) || waveforms[id].Range != WaveformRange.Of(clip)).ToArray()) waveforms.Remove(id);
            Position = Math.Min(Position, IsSourceContext ? sourceDuration : Project?.Duration ?? 0);
            Changed(nameof(NeedsSaveDecision)); Changed(nameof(Title)); StateChanged?.Invoke();
            if (cancellationFailure is not null)
                throw new IOException("The project state was updated, but audio cleanup could not be confirmed. Use Stop to retry: " + cancellationFailure.Message, cancellationFailure);
        }
        if (!response.Ok)
        {
            if (request.Command == "importCPR" && response.Error?.Code == "importPublished") CPRReview = null;
            throw new InvalidOperationException(response.Error?.Message ?? "The shared session rejected this request.");
        }
        return response;
    }
    private async Task Execute(Func<Task> work)
    {
        if (!accepting || closing) return;
        if (pendingActions++ == 0) idle = new(TaskCreationOptions.RunContinuationsAsynchronously);
        Busy = true;
        await actions.WaitAsync();
        try
        {
            if (closing) return;
            await work();
        }
        catch (OperationCanceledException) { Status = "Source preparation cancelled."; }
        catch (Exception error) { Report(error); }
        finally
        {
            actions.Release();
            if (--pendingActions == 0) { Busy = false; idle.TrySetResult(); RequestRuler(); RequestWaveforms(); }
        }
    }
    public void SetRulerViewport(double pixelsPerSecond, double duration)
    {
        var request = new RulerRequest(State.Revision, duration, pixelsPerSecond);
        if (request == desiredRuler) return;
        desiredRuler = request; Ruler = null; RulerError = null; RulerChanged?.Invoke();
        RequestRuler();
    }
    private void RequestRuler()
    {
        if (closing || Busy || !accepting || Project is null || desiredRuler is null || rulerTask is { IsCompleted: false }) return;
        rulerTask = FetchRuler();
    }
    private async Task FetchRuler()
    {
        await Task.Yield();
        while (!closing && accepting && !Busy && Project is not null && desiredRuler is { } request && request.Revision == State.Revision)
        {
            if (request == failedRuler || Ruler is not null && Ruler.Revision == request.Revision && Ruler.Duration == request.Duration && Ruler.PixelsPerSecond == request.PixelsPerSecond) return;
            try
            {
                var reply = await session.Send(new() { Command = "ruler", ExpectedRevision = request.Revision, Value = request.PixelsPerSecond, Duration = request.Duration });
                // Read-only projections never apply the reply's full document
                // state. A delayed ruler cannot roll back a later edit or zoom.
                if (closing || Busy || desiredRuler != request || State.Revision != request.Revision) continue;
                var ruler = reply.Ok ? reply.Ruler : null;
                if (ruler is null) throw new InvalidDataException(reply.Error?.Message ?? "The musical ruler is unavailable.");
                ruler.Validate(request);
                Ruler = ruler; RulerError = null; RulerChanged?.Invoke();
            }
            catch (Exception error)
            {
                if (!closing && desiredRuler == request && State.Revision == request.Revision)
                { failedRuler = request; RulerError = error.Message; RulerChanged?.Invoke(); }
            }
            await Task.Delay(20);
        }
    }
    private void RequestWaveforms()
    {
        if (closing || Busy || !accepting || Project is null || waveformTask is { IsCompleted: false }) return;
        waveformTask = FetchWaveforms();
    }
    private async Task FetchWaveforms()
    {
        // At most one background request is in flight. Yield between clips so
        // an edit waiting for the helper is served before another envelope.
        await Task.Yield();
        while (!closing && accepting && !Busy && Project is not null)
        {
            var clip = Project.Tracks.SelectMany(t => t.Clips).FirstOrDefault(c => !waveforms.ContainsKey(c.Id) &&
                (!waveformFailures.TryGetValue(c.Id, out var failed) || failed != State.Revision));
            if (clip is null) return;
            var revision = State.Revision; var epoch = waveformEpoch; var range = WaveformRange.Of(clip);
            try
            {
                var reply = await session.Send(new() { Command = "waveform", ClipID = clip.Id, ExpectedRevision = revision });
                // The reply's full state is intentionally not applied here.
                // A background reply cannot replace a later user edit.
                var current = Project?.Tracks.SelectMany(t => t.Clips).FirstOrDefault(c => c.Id == clip.Id);
                if (closing || Busy || State.Revision != revision || epoch != waveformEpoch || current is null || WaveformRange.Of(current) != range) continue;
                var envelope = reply.Ok ? reply.Waveform : null;
                if (envelope is null) throw new InvalidDataException("The source waveform is unavailable.");
                envelope.Validate(current, revision);
                waveforms[clip.Id] = (range, envelope); WaveformsChanged?.Invoke();
            }
            catch (Exception) { if (!closing && State.Revision == revision && epoch == waveformEpoch) waveformFailures[clip.Id] = revision; }
            await Task.Delay(20);
        }
    }
    public async Task SuspendAndDrain(bool cancelSourcePreparation = false)
    {
        if (cancelSourcePreparation) CancelSourcePreparation();
        accepting = false; await idle.Task;
    }
    public void ResumeInput() { if (!closing) accepting = true; }
    public object[] HelperModuleReceipt() => session.ModuleReceipt();
    public Task Open(string path, bool asCopy, bool discardChanges) => SourceAction(async () =>
    {
        RequireSaveDecision(discardChanges);
        await Send(new() { Command = "open", Path = path, AsCopy = asCopy, DiscardChanges = discardChanges });
        UseProjectContext();
        Position = 0; Status = asCopy ? "Example opened as a new project. Use Save As to keep your edits." : "Opened " + Project?.Name;
    });
    public Task Command(string command, string? clipID = null, string? trackID = null, double? value = null) => SourceAction(async () =>
    {
        await Send(new() { Command = command, ClipID = clipID, TrackID = trackID, Value = value, Snap = Snap });
        Status = command.StartsWith("select", StringComparison.Ordinal) ? "Selection updated." : "Project updated.";
    });
    public async Task<bool> Save(string? path = null)
    {
        var succeeded = false;
        await Execute(async () =>
        {
            SetSaveConfirmationRequired(true);
            await Send(new() { Command = path is null ? "save" : "saveAs", Path = path });
            SetSaveConfirmationRequired(false);
            Status = "Saved " + Project?.Name;
            succeeded = true;
        });
        return succeeded;
    }
    public Task RenderTo(string path) => Execute(async () =>
    {
        Status = "Rendering…";
        var response = await Send(new() { Command = "render", Path = path });
        var info = response.Render ?? throw new InvalidDataException("The renderer omitted its output metadata.");
        _ = await Task.Run(() => SnapshotReader.Read(info, path, State.Revision));
        Status = "Exported WAV: " + Path.GetFileName(path);
    });
    public Task AttachSourceMedia(string path) => Execute(async () =>
    {
        var selected = SelectedSourceEvent ?? throw new InvalidOperationException("Select a source event before attaching matching PCM media.");
        await Send(new() { Command = "attachSourceMedia", ClipID = selected.Id, Path = path });
        Status = "Media attached to " + selected.Name + ". Save the project to keep the association.";
    });
    public Task InspectSource() => Execute(async () =>
    {
        SourceInspection = null;
        var selected = SelectedSourceEvent ?? throw new InvalidOperationException("Select a retained source event first.");
        var revision = State.Revision;
        Status = "Inspecting source playback modes…";
        var response = await Send(new() { Command = "inspectSourceEvent", ClipID = selected.Id });
        var inspection = response.SourceInspection ?? throw new InvalidDataException("The helper omitted its source inspection.");
        inspection.Validate(revision, selected);
        if (State.Revision != revision || State.Selection.ClipID != selected.Id)
            throw new InvalidDataException("The selected event changed during source inspection.");
        SourceInspection = inspection;
        Status = "Source playback modes inspected; media is checked again for each playback or export.";
    });
    public Task RenderSourceTo(string path, string mode = SourceAuditionMode.Original) => Execute(async () =>
    {
        _ = SourceAuditionMode.Find(mode);
        LastSourceExport = null;
        var selected = SelectedSourceEvent ?? throw new InvalidOperationException("Select a source event before export.");
        var revision = State.Revision;
        Status = "Rendering source event…";
        var response = await Send(new() { Command = "renderSourceEvent", ClipID = selected.Id, Path = path, Mode = mode });
        var info = response.Render ?? throw new InvalidDataException("The renderer omitted its source-event metadata.");
        _ = await Task.Run(() => SnapshotReader.Read(info, path, revision, selected, Project!, mode));
        LastSourceExport = info;
        Status = "Exported source WAV: " + Path.GetFileName(path);
    });
    public Task AuditionSource(string mode = SourceAuditionMode.Original) => SourceAction(async () =>
    {
        _ = SourceAuditionMode.Find(mode);
        var selected = SelectedSourceEvent ?? throw new InvalidOperationException("Select a source event before audition.");
        var seconds = sourceEventID == selected.Id && sourcePlaybackMode == mode ? Position : 0;
        sourcePlaybackMode = mode;
        await PrepareSource(selected.Id, seconds, true, rewindAtEnd: true);
    });
    public Task PlayProject() => SourceAction(async () =>
    {
        if (IsSourceContext) { await InvalidateAudio(); UseProjectContext(); }
        await PlayProjectCore();
    });
    public Task Play() => SourceAction(async () =>
    {
        if (sourceEventID is not null) await PrepareSource(sourceEventID, Position, true, rewindAtEnd: true);
        else await PlayProjectCore();
    });
    private async Task PlayProjectCore()
    {
        if (Project is null) throw new InvalidOperationException("Open a project before playback.");
        audioEpoch++;
        if (loadedRevision == State.Revision)
        {
            if (audioPhase == 4) await SeekLoadedSource(0);
            await audio.Play(); audioPhase = 2; Status = "Playing" + PlaybackFormatSuffix; return;
        }
        var format = await audio.Format();
        ValidateOutputFormat(format);
        Status = "Preparing playback…";
        Directory.CreateDirectory(scratch);
        var path = Path.Combine(scratch, "render-" + Guid.NewGuid().ToString("N") + ".wav");
        var revision = State.Revision;
        try
        {
            var response = await Send(new() { Command = "render", Path = path });
            var info = response.Render ?? throw new InvalidDataException("The renderer omitted its output metadata.");
            var source = await Task.Run(() => SnapshotReader.Read(info, path, revision));
            if (source.SampleRate != Project.SampleRate) throw new InvalidDataException("The project render changed its source sample rate.");
            if (revision != State.Revision) throw new InvalidOperationException("The project changed while rendering. Prepare playback again.");
            await InstallSource(source, revision);
            var frame = (ulong)Math.Clamp(Math.Floor(Position * source.SampleRate), 0, source.Frames);
            if (frame >= source.Frames) frame = 0;
            var current = await SeekLoadedSource(frame);
            if (current.Phase == 4) { Status = "Finished" + PlaybackFormatSuffix; return; }
            await audio.Play(); audioPhase = 2; Status = "Playing" + PlaybackFormatSuffix;
        }
        finally { try { File.Delete(path); } catch (IOException) { } }
    }
    public Task Pause() => Execute(async () =>
    {
        if (loadedRevision is null || audioPhase is not (2 or 7)) return;
        audioEpoch++;
        try
        {
            if (sourceStream is not null)
            {
                ApplyStreamStatus(await sourceStream.Pause());
                PeakLeft = PeakRight = 0; Status = (audioPhase == 4 ? "Finished" : "Paused") + PlaybackFormatSuffix;
                return;
            }
            await audio.Pause();
            // Source audition deliberately reconstructs and revalidates on
            // resume. Preserve the frozen device position before that rebuild;
            // the last UI poll can be older than the actual pause boundary.
            var frozen = await audio.Status();
            ValidateStatus(frozen);
            if (frozen.Phase is not (3 or 4)) throw new InvalidDataException("The native transport did not confirm a paused position.");
            Position = PlaybackPosition(frozen);
            audioPhase = frozen.Phase; PeakLeft = PeakRight = 0;
            Status = (audioPhase == 4 ? "Finished" : "Paused") + PlaybackFormatSuffix;
        }
        catch
        {
            await InvalidateAudio(); Position = 0;
            throw;
        }
    });
    public Task Stop() => SourceAction(async () =>
    {
        audioEpoch++;
        // Keep the installed source available for status/retry if the native
        // stop fails. Explicit Stop must not hide that failure as "Stopped".
        if (sourceStream is not null) { await sourceStream.Cancel(); sourceStream = null; LastSourceStreamWorkerJoined = true; SourcePlaybackStatus = null; }
        else if (loadedRevision is not null) await audio.Stop();
        if (IsSourceContext)
        {
            // A source seek installs a freshly prepared suffix. Its native
            // frame zero is not the full source's zero, so discard it before
            // returning the UI to the beginning and allowing another play.
            loadedRevision = null; PlaybackRateInfo = null; sourceStartFrame = 0;
        }
        audioPhase = loadedRevision is null ? 0u : 1u; Position = 0; PeakLeft = PeakRight = 0; Status = "Stopped";
    });
    public Task Seek(double seconds) => SourceAction(async () =>
    {
        if (!double.IsFinite(seconds)) throw new InvalidOperationException("Enter a finite playhead time.");
        if (sourceEventID is not null)
        {
            await PrepareSource(sourceEventID, Math.Max(0, seconds), IsPlaying, rewindAtEnd: false);
            return;
        }
        await SeekProjectCore(seconds);
    });
    public Task SeekProject(double seconds) => SourceAction(async () =>
    {
        if (!double.IsFinite(seconds)) throw new InvalidOperationException("Enter a finite playhead time.");
        if (IsSourceContext) { await InvalidateAudio(); UseProjectContext(); }
        await SeekProjectCore(seconds);
    });
    private async Task SeekProjectCore(double seconds)
    {
        audioEpoch++;
        Position = Math.Clamp(seconds, 0, Project?.Duration ?? 0);
        if (loadedRevision is not null && Project is not null)
        {
            await SeekLoadedSource((ulong)Math.Floor(Position * PlaybackRateInfo!.Value.SourceRate));
        }
    }
    public async Task Poll()
    {
        if (polling || Busy || closing || loadedRevision is null) return;
        polling = true;
        var revision = loadedRevision;
        var epoch = audioEpoch;
        try
        {
            if (sourceStream is { } running)
            {
                var streamStatus = await running.Status();
                if (sourceStream != running || loadedRevision != revision || audioEpoch != epoch || Busy || closing) return;
                ApplyStreamStatus(streamStatus);
                if (streamStatus.Phase == 4) Status = "Finished";
                else if (streamStatus.Phase == 7) Status = "Draining source stream" + PlaybackFormatSuffix;
                return;
            }
            var snapshot = await audio.Status();
            if (loadedRevision != revision || audioEpoch != epoch || Busy || closing) return;
            ValidateStatus(snapshot);
            audioPhase = snapshot.Phase;
            Position = PlaybackPosition(snapshot);
            PeakLeft = snapshot.PeakLeft; PeakRight = snapshot.PeakRight;
            if (snapshot.Phase == 4) Status = "Finished";
        }
        catch (Exception error)
        {
            if (loadedRevision != revision || audioEpoch != epoch || Busy || closing) return;
            try { await InvalidateAudio(); Report(error); }
            catch (Exception cancellationError)
            {
                // Retain the installed generation for an explicit Stop retry.
                // A timer callback must not escape without reporting failure.
                audioPhase = 5; PeakLeft = PeakRight = 0;
                Report(new IOException(error.Message + " Stop could not be confirmed: " + cancellationError.Message, cancellationError));
            }
        }
        finally { polling = false; }
    }
    public async ValueTask DisposeAsync()
    {
        closing = true; CancelSourcePreparation();
        sourceStream?.RequestCancel();
        await session.DisposeAsync();
        await Task.WhenAll(abandonedTickets);
        if (waveformTask is not null) await waveformTask;
        if (rulerTask is not null) await rulerTask;
        await actions.WaitAsync();
        try
        {
            try { if (sourceStream is not null) await sourceStream.DisposeAsync(); }
            finally { await audio.DisposeAsync(); }
        }
        finally { actions.Release(); }
        try { if (Directory.Exists(scratch)) Directory.Delete(scratch, recursive: true); }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }
}
