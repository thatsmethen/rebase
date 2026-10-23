using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace Rebase.Windows;

public sealed class StudioViewModel : INotifyPropertyChanged, IAsyncDisposable
{
    private readonly ISessionClient session;
    private readonly IAudioOutput audio;
    private readonly string scratch = Path.Combine(Path.GetTempPath(), "Rebase", Guid.NewGuid().ToString("N"));
    private readonly SemaphoreSlim actions = new(1, 1);
    private ulong? loadedRevision;
    private ulong audioEpoch;
    private string? sourceEventID;
    private double sourceDuration, projectPosition;
    private readonly Dictionary<string, (WaveformRange Range, WaveformSnapshot Snapshot)> waveforms = [];
    private readonly Dictionary<string, ulong> waveformFailures = [];
    private Task? waveformTask;
    private ulong waveformEpoch;
    private bool polling, closing;
    private uint audioPhase;
    private bool accepting = true;
    private int pendingActions;
    private TaskCompletionSource idle = CompletedIdle();
    private static TaskCompletionSource CompletedIdle() { var source = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously); source.SetResult(); return source; }
    private string status = "Open a project, or explore the included example.";
    private bool busy;
    private double position, peakLeft, peakRight;
    public StudioViewModel(ISessionClient? session = null, IAudioOutput? audio = null)
    {
        this.session = session ?? new SessionProcess();
        this.audio = audio ?? new NativeAudio();
    }
    public SessionState State { get; private set; } = new();
    public RenderSnapshot? LastSourceExport { get; private set; }
    public ProjectView? Project => State.Project;
    public TrackView? SelectedTrack => Project?.Tracks.FirstOrDefault(t => t.Id == State.Selection.TrackID);
    public ClipView? SelectedClip => Project?.Tracks.SelectMany(t => t.Clips).FirstOrDefault(c => c.Id == State.Selection.ClipID);
    public SourceEventView[] SourceEvents => SourceEventView.Read(Project);
    public SourceEventView? SelectedSourceEvent => SourceEvents.FirstOrDefault(e => e.Id == State.Selection.ClipID);
    public bool IsSourceContext => sourceEventID is not null;
    public string TransportContext => sourceEventID is null ? "Project timeline" :
        "Source event: " + (SourceEvents.FirstOrDefault(e => e.Id == sourceEventID)?.Name ?? "Unavailable") + " · event-local seconds";
    public string Title => (Project?.Name ?? "Rebase") + (State.Dirty ? " •" : "") + " — Rebase";
    public string Status { get => status; private set { status = value; Changed(); } }
    public bool Busy { get => busy; private set { busy = value; Changed(); } }
    public double Position { get => position; private set { position = value; Changed(); } }
    public double PeakLeft { get => peakLeft; private set { peakLeft = value; Changed(); } }
    public double PeakRight { get => peakRight; private set { peakRight = value; Changed(); } }
    public string Snap { get; set; } = "off";
    public bool IsPlaying => audioPhase == 2;
    public event PropertyChangedEventHandler? PropertyChanged;
    public event Action? StateChanged;
    public event Action? WaveformsChanged;
    public IReadOnlyDictionary<string, float[]> WaveformPeaks => waveforms.ToDictionary(item => item.Key, item => item.Value.Snapshot.Peaks);
    private void Changed([CallerMemberName] string? property = null) => PropertyChanged?.Invoke(this, new(property));
    public void Report(Exception error) => Status = error.Message;
    private void NotifyContext() { Changed(nameof(IsSourceContext)); Changed(nameof(TransportContext)); }
    private void UseProjectContext()
    {
        var wasSource = sourceEventID is not null;
        sourceEventID = null; sourceDuration = 0;
        if (wasSource) Position = Math.Min(projectPosition, Project?.Duration ?? 0);
        NotifyContext();
    }
    private async Task InvalidateAudio()
    {
        audioEpoch++;
        if (loadedRevision is null) return;
        try { await audio.Stop(); }
        catch (IOException error) { Report(error); }
        finally { loadedRevision = null; audioPhase = 0; PeakLeft = PeakRight = 0; }
    }
    private async Task<SessionResponse> Send(SessionRequest request)
    {
        request.ExpectedRevision = State.Revision;
        var response = await session.Send(request);
        if (response.State is not null)
        {
            if (State.Revision != response.State.Revision) { await InvalidateAudio(); UseProjectContext(); }
            State = response.State;
            if (response.Ok && request.Command is "open" or "saveAs")
            {
                waveformEpoch++; waveforms.Clear(); waveformFailures.Clear();
            }
            var clips = Project?.Tracks.SelectMany(t => t.Clips).ToDictionary(c => c.Id) ?? [];
            foreach (var id in waveforms.Keys.Where(id => !clips.TryGetValue(id, out var clip) || waveforms[id].Range != WaveformRange.Of(clip)).ToArray()) waveforms.Remove(id);
            if (sourceEventID is not null && sourceEventID != State.Selection.ClipID)
            {
                await InvalidateAudio(); UseProjectContext();
            }
            Position = Math.Min(Position, IsSourceContext ? sourceDuration : Project?.Duration ?? 0);
            Changed(nameof(Title)); StateChanged?.Invoke();
        }
        if (!response.Ok) throw new InvalidOperationException(response.Error?.Message ?? "The shared session rejected this request.");
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
        catch (Exception error) { Report(error); }
        finally
        {
            actions.Release();
            if (--pendingActions == 0) { Busy = false; idle.TrySetResult(); RequestWaveforms(); }
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
    public async Task SuspendAndDrain() { accepting = false; await idle.Task; }
    public void ResumeInput() { if (!closing) accepting = true; }
    public object[] HelperModuleReceipt() => session.ModuleReceipt();
    public Task Open(string path, bool asCopy, bool discardChanges) => Execute(async () =>
    {
        await Send(new() { Command = "open", Path = path, AsCopy = asCopy, DiscardChanges = discardChanges });
        UseProjectContext();
        Position = 0; Status = asCopy ? "Example opened as a new project. Use Save As to keep your edits." : "Opened " + Project?.Name;
    });
    public Task Command(string command, string? clipID = null, string? trackID = null, double? value = null) => Execute(async () =>
    {
        await Send(new() { Command = command, ClipID = clipID, TrackID = trackID, Value = value, Snap = Snap });
        Status = command.StartsWith("select", StringComparison.Ordinal) ? "Selection updated." : "Project updated.";
    });
    public Task Save(string? path = null) => Execute(async () =>
    {
        await Send(new() { Command = path is null ? "save" : "saveAs", Path = path });
        Status = "Saved " + Project?.Name;
    });
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
    public Task RenderSourceTo(string path) => Execute(async () =>
    {
        LastSourceExport = null;
        var selected = SelectedSourceEvent ?? throw new InvalidOperationException("Select a source event before export.");
        var revision = State.Revision;
        Status = "Rendering source event…";
        var response = await Send(new() { Command = "renderSourceEvent", ClipID = selected.Id, Path = path });
        var info = response.Render ?? throw new InvalidDataException("The renderer omitted its source-event metadata.");
        _ = await Task.Run(() => SnapshotReader.Read(info, path, revision, selected));
        LastSourceExport = info;
        Status = "Exported source WAV: " + Path.GetFileName(path);
    });
    public Task AuditionSource() => Execute(async () =>
    {
        var selected = SelectedSourceEvent ?? throw new InvalidOperationException("Select a source event before audition.");
        await PrepareSource(selected.Id, sourceEventID == selected.Id ? Position : 0, true, rewindAtEnd: true);
    });
    public Task PlayProject() => Execute(async () =>
    {
        if (IsSourceContext) { await InvalidateAudio(); UseProjectContext(); }
        await PlayProjectCore();
    });
    public Task Play() => Execute(async () =>
    {
        if (sourceEventID is not null) await PrepareSource(sourceEventID, Position, true, rewindAtEnd: true);
        else await PlayProjectCore();
    });
    private async Task PlayProjectCore()
    {
        if (Project is null) throw new InvalidOperationException("Open a project before playback.");
        if (loadedRevision == State.Revision)
        {
            if (audioPhase == 4) { await audio.Seek(0); Position = 0; }
            await audio.Play(); audioPhase = 2; Status = "Playing"; return;
        }
        var format = await audio.Format();
        if (format.Float32 != 1 || format.Channels != 2 || format.SampleRate != Project.SampleRate)
            throw new InvalidOperationException($"This project uses {Project.SampleRate:0} Hz. The default output must use Float32 stereo at the same rate ({format.SampleRate} Hz currently). Device-rate conversion is not yet available.");
        Status = "Preparing playback…";
        Directory.CreateDirectory(scratch);
        var path = Path.Combine(scratch, "render-" + Guid.NewGuid().ToString("N") + ".wav");
        var revision = State.Revision;
        try
        {
            var response = await Send(new() { Command = "render", Path = path });
            var info = response.Render ?? throw new InvalidDataException("The renderer omitted its output metadata.");
            var source = await Task.Run(() => SnapshotReader.Read(info, path, revision));
            if (revision != State.Revision) throw new InvalidOperationException("The project changed while rendering. Prepare playback again.");
            await audio.SetSource(source);
            loadedRevision = revision; audioPhase = 1;
            var frame = (ulong)Math.Clamp(Math.Floor(Position * source.SampleRate), 0, source.Frames);
            if (frame >= source.Frames) frame = 0;
            await audio.Seek(frame);
            await audio.Play(); audioPhase = 2; Status = "Playing";
        }
        finally { try { File.Delete(path); } catch (IOException) { } }
    }
    private async Task PrepareSource(string id, double seconds, bool play, bool rewindAtEnd)
    {
        var selected = SelectedSourceEvent;
        if (selected is null || selected.Id != id) throw new InvalidOperationException("Select the source event again before audition.");
        var revision = State.Revision;
        await InvalidateAudio();
        if (!IsSourceContext) projectPosition = Position;
        sourceEventID = id; NotifyContext();
        Status = "Checking source and attached media…";
        Directory.CreateDirectory(scratch);
        var path = Path.Combine(scratch, "source-" + Guid.NewGuid().ToString("N") + ".wav");
        try
        {
            // Every play/resume and seek asks Swift to re-check the retained
            // source and attached media. A cached revision never authorizes it.
            var response = await Send(new() { Command = "renderSourceEvent", ClipID = id, Path = path });
            var info = response.Render ?? throw new InvalidDataException("The renderer omitted its source-event metadata.");
            var source = await Task.Run(() => SnapshotReader.Read(info, path, revision, selected));
            if (State.Revision != revision || State.Selection.ClipID != id) throw new InvalidOperationException("The selected source event changed while rendering.");
            var format = await audio.Format();
            if (format.Float32 != 1 || format.Channels != 2 || format.SampleRate != source.SampleRate)
                throw new InvalidOperationException($"This source event uses {source.SampleRate} Hz. The default output must use Float32 stereo at that exact rate ({format.SampleRate} Hz currently). Device-rate conversion is not yet available.");
            await audio.SetSource(source);
            loadedRevision = revision; audioPhase = 1;
            sourceDuration = (double)source.Frames / source.SampleRate;
            var frame = (ulong)Math.Clamp(Math.Round(seconds * source.SampleRate, MidpointRounding.AwayFromZero), 0, source.Frames);
            if (rewindAtEnd && frame == source.Frames) frame = 0;
            await audio.Seek(frame); Position = (double)frame / source.SampleRate;
            if (play && frame < source.Frames) { await audio.Play(); audioPhase = 2; }
            else if (frame == source.Frames) audioPhase = 4;
            Status = audioPhase == 2 ? "Auditioning source: " + selected.Name : "Source position updated; source and media rechecked.";
        }
        finally { try { File.Delete(path); } catch (IOException) { } }
    }
    public Task Pause() => Execute(async () =>
    {
        if (loadedRevision is null || audioPhase != 2) return;
        audioEpoch++;
        await audio.Pause(); audioPhase = 3; PeakLeft = PeakRight = 0; Status = "Paused";
    });
    public Task Stop() => Execute(async () =>
    {
        audioEpoch++;
        if (loadedRevision is not null) await audio.Stop();
        audioPhase = loadedRevision is null ? 0u : 1u; Position = 0; PeakLeft = PeakRight = 0; Status = "Stopped";
    });
    public Task Seek(double seconds) => Execute(async () =>
    {
        if (!double.IsFinite(seconds)) throw new InvalidOperationException("Enter a finite playhead time.");
        if (sourceEventID is not null)
        {
            await PrepareSource(sourceEventID, Math.Max(0, seconds), IsPlaying, rewindAtEnd: false);
            return;
        }
        await SeekProjectCore(seconds);
    });
    public Task SeekProject(double seconds) => Execute(async () =>
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
            await audio.Seek((ulong)Math.Floor(Position * Project.SampleRate));
            var current = await audio.Status(); audioPhase = current.Phase;
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
            var snapshot = await audio.Status();
            if (loadedRevision != revision || audioEpoch != epoch || Busy || closing) return;
            audioPhase = snapshot.Phase;
            Position = snapshot.SampleRate == 0 ? 0 : (double)snapshot.PositionFrames / snapshot.SampleRate;
            PeakLeft = snapshot.PeakLeft; PeakRight = snapshot.PeakRight;
            if (snapshot.Phase == 4) Status = "Finished";
        }
        catch (Exception error)
        {
            if (loadedRevision != revision || audioEpoch != epoch || Busy || closing) return;
            loadedRevision = null; audioPhase = 0; PeakLeft = PeakRight = 0; Report(error);
        }
        finally { polling = false; }
    }
    public async ValueTask DisposeAsync()
    {
        closing = true;
        await session.DisposeAsync();
        if (waveformTask is not null) await waveformTask;
        await actions.WaitAsync();
        try { await audio.DisposeAsync(); }
        finally { actions.Release(); }
        try { if (Directory.Exists(scratch)) Directory.Delete(scratch, recursive: true); }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }
}
