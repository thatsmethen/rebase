namespace Rebase.Windows;

public sealed partial class StudioViewModel
{
    private readonly ISourceStreamFactory streamFactory;
    private SourceStreamPlayback? sourceStream;
    private CancellationTokenSource? sourcePreparation;
    private ulong nextSourceGeneration;
    private readonly List<Task> abandonedTickets = [];
    public IReadOnlyDictionary<string, ulong> HelperRequestCounts() => session is ISessionRequestObservation observed
        ? observed.DispatchedCommandCounts() : throw new InvalidOperationException("This session has no dispatched-request observer.");
    public bool LastSourceStreamWorkerJoined { get; private set; }
    public bool LastSourceStreamNativeStarted { get; private set; }
    public int? LastSourceStreamNativeError { get; private set; }
    public bool SourceStreamPreparing => sourcePreparation is not null;
    public AudioStreamStatus? SourcePlaybackStatus { get; private set; }
    public SourceStreamAdmission? LastSourceStreamAdmission { get; private set; }

    private void CancelSourcePreparation()
    {
        sourcePreparation?.Cancel();
    }
    private Task SourceAction(Func<Task> work)
    {
        // Interrupt an in-flight source preparation before joining the normal
        // UI action queue. The editing process itself is never cancelled.
        CancelSourcePreparation();
        return Execute(work);
    }
    private void ApplyStreamStatus(AudioStreamStatus current)
    {
        SourcePlaybackStatus = current; PlaybackRateInfo = current.RateInfo;
        audioPhase = current.Phase;
        Position = (double)(sourceStartFrame + current.SourcePosition) / current.SourceRate;
        PeakLeft = current.PeakLeft; PeakRight = current.PeakRight;
    }
    private async Task ObserveAbandonedTicket(Task<SessionResponse> pending, string path)
    {
        // Send still owns its request/response framing. Wait in the background
        // only to remove this private late ticket; never apply its old state.
        try { await pending; } catch (Exception) { }
        DeleteTicket(path);
    }
    private static void DeleteTicket(string path)
    {
        try { File.Delete(path); }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }
    private async Task PrepareSource(string id, double seconds, bool play, bool rewindAtEnd)
    {
        var selected = SelectedSourceEvent;
        if (selected is null || selected.Id != id) throw new InvalidOperationException("Select the source event again before audition.");
        var revision = State.Revision;
        var mode = sourcePlaybackMode;
        await InvalidateAudio();
        if (!IsSourceContext) projectPosition = Position;
        sourceEventID = id; NotifyContext();
        LastSourceStreamAdmission = null; LastSourceStreamWorkerJoined = false; LastSourceStreamNativeStarted = false; LastSourceStreamNativeError = null;
        using var preparing = new CancellationTokenSource();
        sourcePreparation = preparing; Changed(nameof(SourceStreamPreparing));
        Status = "Checking source and attached media…";
        Directory.CreateDirectory(scratch);
        var path = Path.Combine(scratch, "source-" + Guid.NewGuid().ToString("N") + ".ticket");
        ISourceStream? worker = null;
        SourceStreamPlayback? candidate = null;
        var lateTicket = false;
        try
        {
            var pending = session.Send(new() { Command = "prepareSourceStream", ClipID = id, Path = path,
                ExpectedRevision = revision, Mode = mode, StartSeconds = seconds, RewindAtEnd = rewindAtEnd });
            SessionResponse response;
            try { response = await pending.WaitAsync(preparing.Token); }
            catch (OperationCanceledException)
            {
                lateTicket = true;
                abandonedTickets.RemoveAll(task => task.IsCompleted);
                abandonedTickets.Add(ObserveAbandonedTicket(pending, path));
                throw;
            }
            if (!response.Ok) throw new InvalidOperationException(response.Error?.Message ?? "The shared helper rejected source preparation.");
            if (response.State is null || response.State.Revision != revision || response.State.Selection.ClipID != id ||
                State.Revision != revision || State.Selection.ClipID != id || mode != sourcePlaybackMode)
                throw new InvalidDataException("The source preparation belongs to a changed document or selection.");
            var ticket = response.SourceStream ?? throw new InvalidDataException("The helper omitted its source stream ticket.");
            ticket.Validate(path, revision, selected, mode);
            preparing.Token.ThrowIfCancellationRequested();
            worker = await streamFactory.Open(ticket, selected, Project!, preparing.Token);
            preparing.Token.ThrowIfCancellationRequested();
            DeleteTicket(path);
            sourceStartFrame = ticket.StartFrame;
            sourceDuration = (double)ticket.TotalFrames / ticket.SampleRate;
            Position = (double)sourceStartFrame / ticket.SampleRate;
            LastSourceStreamAdmission = worker.Admission;
            if (ticket.Frames == 0)
            {
                if (await worker.Read(preparing.Token) is not null) throw new InvalidDataException("A source EOF preparation emitted PCM.");
                audioPhase = 4; Status = "Finished; source and media rechecked."; return;
            }
            if (audio is not IAudioStreamOutput output) throw new InvalidOperationException("This audio adapter does not support bounded source streaming.");
            var format = await audio.Format(); ValidateOutputFormat(format);
            preparing.Token.ThrowIfCancellationRequested();
            var descriptor = AudioStreamDescriptor.For(ticket, checked(++nextSourceGeneration));
            candidate = new(worker, output, descriptor); worker = null;
            Status = "Priming source stream…";
            var ready = await candidate.Prime(preparing.Token);
            LastSourceStreamNativeStarted = true;
            preparing.Token.ThrowIfCancellationRequested();
            if (State.Revision != revision || State.Selection.ClipID != id || mode != sourcePlaybackMode)
                throw new InvalidDataException("The selected source changed during stream preparation.");
            sourceStream = candidate; candidate = null; loadedRevision = revision;
            ApplyStreamStatus(ready);
            if (play && audioPhase != 4) { await sourceStream.Play(); audioPhase = 2; }
            Status = (audioPhase == 2 ? "Streaming source: " + selected.Name : "Source position updated; source and media rechecked.") + PlaybackFormatSuffix;
        }
        catch (Exception preparationError)
        {
            if (preparationError is NativeAudioException nativeFailure) LastSourceStreamNativeError = nativeFailure.Code;
            var failed = sourceStream ?? candidate;
            if (failed is not null)
            {
                LastSourceStreamNativeStarted |= failed.NativeInstalled;
                try { await failed.Cancel(); LastSourceStreamWorkerJoined = true; }
                catch (Exception cancellationError)
                {
                    // Keep the generation reachable for Stop even when prime,
                    // Play, or proof/refill failure is followed by device loss.
                    sourceStream = failed; candidate = null; loadedRevision = revision;
                    audioPhase = 5; PeakLeft = PeakRight = 0;
                    throw new IOException(preparationError.Message +
                        " Stream cleanup could not be confirmed. Use Stop to retry: " + cancellationError.Message, cancellationError);
                }
                sourceStream = null; candidate = null; loadedRevision = null;
            }
            PlaybackRateInfo = null; SourcePlaybackStatus = null; audioPhase = 0; PeakLeft = PeakRight = 0;
            throw;
        }
        finally
        {
            try
            {
                if (candidate is not null) await candidate.Cancel();
                if (worker is not null) { await worker.DisposeAsync(); LastSourceStreamWorkerJoined = true; }
            }
            finally
            {
                sourcePreparation = null; Changed(nameof(SourceStreamPreparing));
                if (!lateTicket) DeleteTicket(path);
            }
        }
    }
}
