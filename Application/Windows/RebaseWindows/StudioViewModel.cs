using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace Rebase.Windows;

public sealed class StudioViewModel : INotifyPropertyChanged, IAsyncDisposable
{
    private readonly SessionProcess session = new();
    private readonly NativeAudio audio = new();
    private readonly string scratch = Path.Combine(Path.GetTempPath(), "Rebase", Guid.NewGuid().ToString("N"));
    private readonly SemaphoreSlim actions = new(1, 1);
    private ulong? loadedRevision;
    private bool polling, closing;
    private uint audioPhase;
    private bool accepting = true;
    private int pendingActions;
    private TaskCompletionSource idle = CompletedIdle();
    private static TaskCompletionSource CompletedIdle() { var source = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously); source.SetResult(); return source; }
    private string status = "Open a project, or explore the included example.";
    private bool busy;
    private double position, peakLeft, peakRight;
    public SessionState State { get; private set; } = new();
    public ProjectView? Project => State.Project;
    public TrackView? SelectedTrack => Project?.Tracks.FirstOrDefault(t => t.Id == State.Selection.TrackID);
    public ClipView? SelectedClip => Project?.Tracks.SelectMany(t => t.Clips).FirstOrDefault(c => c.Id == State.Selection.ClipID);
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
    private void Changed([CallerMemberName] string? property = null) => PropertyChanged?.Invoke(this, new(property));
    public void Report(Exception error) => Status = error.Message;
    private async Task InvalidateAudio()
    {
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
            if (State.Revision != response.State.Revision) await InvalidateAudio();
            State = response.State;
            Position = Math.Min(Position, Project?.Duration ?? 0);
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
            if (--pendingActions == 0) { Busy = false; idle.TrySetResult(); }
        }
    }
    public async Task SuspendAndDrain() { accepting = false; await idle.Task; }
    public void ResumeInput() { if (!closing) accepting = true; }
    public object[] HelperModuleReceipt() => session.ModuleReceipt();
    public Task Open(string path, bool asCopy, bool discardChanges) => Execute(async () =>
    {
        await Send(new() { Command = "open", Path = path, AsCopy = asCopy, DiscardChanges = discardChanges });
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
    public Task Play() => Execute(async () =>
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
    });
    public Task Pause() => Execute(async () =>
    {
        if (loadedRevision is null || audioPhase != 2) return;
        await audio.Pause(); audioPhase = 3; PeakLeft = PeakRight = 0; Status = "Paused";
    });
    public Task Stop() => Execute(async () =>
    {
        if (loadedRevision is not null) await audio.Stop();
        audioPhase = loadedRevision is null ? 0u : 1u; Position = 0; PeakLeft = PeakRight = 0; Status = "Stopped";
    });
    public Task Seek(double seconds) => Execute(async () =>
    {
        if (!double.IsFinite(seconds)) throw new InvalidOperationException("Enter a finite playhead time.");
        Position = Math.Clamp(seconds, 0, Project?.Duration ?? 0);
        if (loadedRevision is not null && Project is not null)
        {
            await audio.Seek((ulong)Math.Floor(Position * Project.SampleRate));
            var current = await audio.Status(); audioPhase = current.Phase;
        }
    });
    public async Task Poll()
    {
        if (polling || Busy || closing || loadedRevision is null) return;
        polling = true;
        var revision = loadedRevision;
        try
        {
            var snapshot = await audio.Status();
            if (loadedRevision != revision || Busy || closing) return;
            audioPhase = snapshot.Phase;
            Position = snapshot.SampleRate == 0 ? 0 : (double)snapshot.PositionFrames / snapshot.SampleRate;
            PeakLeft = snapshot.PeakLeft; PeakRight = snapshot.PeakRight;
            if (snapshot.Phase == 4) Status = "Finished";
        }
        catch (Exception error) { loadedRevision = null; audioPhase = 0; PeakLeft = PeakRight = 0; Report(error); }
        finally { polling = false; }
    }
    public async ValueTask DisposeAsync()
    {
        closing = true;
        await session.DisposeAsync();
        await actions.WaitAsync();
        try { await audio.DisposeAsync(); }
        finally { actions.Release(); }
        try { if (Directory.Exists(scratch)) Directory.Delete(scratch, recursive: true); }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }
}
