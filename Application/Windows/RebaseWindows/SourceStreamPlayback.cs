namespace Rebase.Windows;

// One immutable worker generation feeds one native generation. Backpressure
// waits live here, outside every native/control lock and outside the UI queue.
public sealed class SourceStreamPlayback(ISourceStream worker, IAudioStreamOutput output,
    AudioStreamDescriptor descriptor) : IAsyncDisposable
{
    private readonly CancellationTokenSource cancellation = new();
    private Task? pump;
    private readonly SemaphoreSlim cancelGate = new(1, 1);
    private readonly object lifetimeGate = new();
    private Exception? failure;
    private bool installed, terminal, disposed;
    public SourceStreamTicket Ticket => worker.Admission.Ticket;
    public AudioStreamDescriptor Descriptor => descriptor;
    public Exception? Failure => Volatile.Read(ref failure);
    public bool NativeInstalled => installed;
    public bool TerminalVerified => Volatile.Read(ref terminal);

    public async Task<AudioStreamStatus> Prime(CancellationToken preparing)
    {
        if (installed) throw new InvalidOperationException("Source stream was already installed.");
        preparing.ThrowIfCancellationRequested();
        await output.BeginStream(descriptor);
        installed = true;
        pump = Task.Run(Pump);
        using var interrupted = preparing.Register(RequestCancel);
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(preparing, cancellation.Token);
        deadline.CancelAfter(TimeSpan.FromSeconds(120));
        while (true)
        {
            deadline.Token.ThrowIfCancellationRequested();
            var status = await Status();
            if (status.Primed == 1) return status;
            await Task.Delay(5, deadline.Token);
        }
    }
    private async Task Pump()
    {
        try
        {
            ulong sequence = 0, frames = 0;
            while (await worker.Read(cancellation.Token) is { } chunk)
            {
                cancellation.Token.ThrowIfCancellationRequested();
                while (!await output.SubmitStream(descriptor.Generation, sequence,
                    chunk.AbsoluteFrame - Ticket.StartFrame, chunk.Samples, chunk.Frames))
                    await Task.Delay(5, cancellation.Token);
                sequence = checked(sequence + 1); frames = checked(frames + chunk.Frames);
            }
            cancellation.Token.ThrowIfCancellationRequested();
            // Worker.Read(null) also confirms terminal bytes and clean process
            // exit. Only then may the converter drain its true final tail.
            Volatile.Write(ref terminal, true);
            await output.FinishStream(descriptor.Generation, sequence, frames);
        }
        catch (Exception error)
        {
            if (!cancellation.IsCancellationRequested) Volatile.Write(ref failure, error);
            worker.RequestCancel();
        }
    }
    public async Task<AudioStreamStatus> Status()
    {
        if (Failure is { } error) throw new IOException("Source streaming failed. " + error.Message, error);
        var status = await output.StreamStatus(descriptor.Generation);
        status.Validate(descriptor);
        if (status.Phase == 4 && !TerminalVerified)
            throw new InvalidDataException("The device completed before a verified source EOF.");
        return status;
    }
    public Task Play() => output.PlayStream(descriptor.Generation);
    public async Task<AudioStreamStatus> Pause()
    {
        await output.PauseStream(descriptor.Generation);
        var frozen = await Status();
        if (frozen.Phase is not (3 or 4)) throw new InvalidDataException("The source stream did not confirm a frozen device position.");
        return frozen;
    }
    public void RequestCancel()
    {
        lock (lifetimeGate) { if (disposed) return; cancellation.Cancel(); worker.RequestCancel(); }
    }
    public async Task Cancel()
    {
        await cancelGate.WaitAsync();
        try
        {
            if (disposed) return;
            // Failure retains the native generation for diagnostic/Stop retry.
            if (installed) await output.CancelStream(descriptor.Generation);
            installed = false;
            RequestCancel();
            if (pump is not null) await pump;
            await worker.DisposeAsync();
            lock (lifetimeGate) { disposed = true; cancellation.Dispose(); }
        }
        finally { cancelGate.Release(); }
    }
    public async ValueTask DisposeAsync()
    {
        if (disposed) return;
        try { await Cancel(); }
        finally
        {
            if (!disposed)
            {
                // A device fault must not strand the dedicated process. Native
                // handle destruction is the final device barrier on app close.
                RequestCancel(); if (pump is not null) await pump;
                await worker.DisposeAsync();
                lock (lifetimeGate) { disposed = true; cancellation.Dispose(); }
            }
        }
    }
}
