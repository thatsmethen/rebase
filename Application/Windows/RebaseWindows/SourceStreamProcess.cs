using System.Diagnostics;
using System.ComponentModel;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Rebase.Windows;

public interface ISourceStream : IAsyncDisposable
{
    SourceStreamAdmission Admission { get; }
    Task<SourceStreamChunk?> Read(CancellationToken cancellation);
    // Synchronous cancellation closes the pipe and interrupts a blocked child.
    // DisposeAsync is the subsequent join barrier, never the first signal.
    void RequestCancel();
}
public interface ISourceStreamFactory
{
    Task<ISourceStream> Open(SourceStreamTicket ticket, SourceEventView selected, ProjectView project, CancellationToken cancellation);
}
public sealed class SourceStreamProcessFactory(string? executablePath = null) : ISourceStreamFactory
{
    public Task<ISourceStream> Open(SourceStreamTicket ticket, SourceEventView selected, ProjectView project, CancellationToken cancellation) =>
        SourceStreamProcess.Open(ticket, selected, project, cancellation, executablePath);
}

public sealed class SourceStreamProcess : ISourceStream
{
    private readonly Process child;
    private readonly SourceStreamReader reader;
    private readonly CancellationTokenSource lifetime = new();
    private readonly Task stderrDrain;
    private int cancelled, disposed;
    private readonly object shutdownGate = new();
    private readonly SemaphoreSlim disposeGate = new(1, 1);
    private Exception? terminationError;
    public SourceStreamAdmission Admission { get; private set; } = null!;

    private SourceStreamProcess(Process child)
    {
        this.child = child;
        reader = new(child.StandardOutput.BaseStream);
        stderrDrain = DrainError();
    }
    public static async Task<ISourceStream> Open(SourceStreamTicket ticket, SourceEventView selected,
        ProjectView project, CancellationToken cancellation, string? executablePath = null)
    {
        cancellation.ThrowIfCancellationRequested();
        // Reject symlink/reparse aliases before allowing the worker to read a
        // ticket. Its independent implementation also verifies all ancestors.
        var path = Path.GetFullPath(ticket.TicketPath);
        for (FileSystemInfo? item = new FileInfo(path); item is not null; item = item is FileInfo file ? file.Directory : ((DirectoryInfo)item).Parent)
            SourceStreamWire.Require((item.Attributes & FileAttributes.ReparsePoint) == 0, "The source ticket path contains a link.");
        var fileInfo = new FileInfo(path);
        SourceStreamWire.Require(fileInfo.Length is > 0 and <= 32 * 1024 * 1024, "The source ticket exceeds its preparation bound.");
        await using (var file = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 65536, FileOptions.Asynchronous | FileOptions.SequentialScan))
        {
            var digest = Convert.ToHexStringLower(await SHA256.HashDataAsync(file, cancellation));
            SourceStreamWire.Require(digest == ticket.TicketSHA256, "The source ticket changed before worker admission.");
        }
        var executable = executablePath ?? Path.Combine(AppContext.BaseDirectory, "rebase-session.exe");
        if (!File.Exists(executable)) throw new FileNotFoundException("The release is missing its source worker. Keep the complete application folder together.");
        var start = new ProcessStartInfo(executable)
        {
            UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = AppContext.BaseDirectory,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false), StandardErrorEncoding = new UTF8Encoding(false)
        };
        start.ArgumentList.Add("--source-stream");
        var child = Process.Start(start) ?? throw new IOException("The source worker could not start.");
        var worker = new SourceStreamProcess(child);
        try
        {
            using var external = cancellation.Register(worker.RequestCancel);
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellation, worker.lifetime.Token);
            deadline.CancelAfter(TimeSpan.FromSeconds(120));
            var startup = JsonSerializer.Serialize(new
            {
                schema = "rebase.source-stream-start.v1", ticketPath = path, ticketSHA256 = ticket.TicketSHA256,
                capability = ticket.Capability, generation = ticket.Generation
            });
            SourceStreamWire.Require(Encoding.UTF8.GetByteCount(startup) <= 65536, "The source startup request exceeds its bound.");
            child.StandardInput.NewLine = "\n";
            await child.StandardInput.WriteLineAsync(startup.AsMemory(), deadline.Token);
            await child.StandardInput.FlushAsync(deadline.Token);
            child.StandardInput.Close();
            worker.Admission = await worker.reader.Admit(ticket, selected, project, deadline.Token);
            return worker;
        }
        catch { await worker.DisposeAsync(); throw; }
    }
    public async Task<SourceStreamChunk?> Read(CancellationToken cancellation)
    {
        using var external = cancellation.Register(RequestCancel);
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellation, lifetime.Token);
        deadline.CancelAfter(TimeSpan.FromSeconds(120));
        try
        {
            var chunk = await reader.Read(deadline.Token);
            if (chunk is null)
            {
                await child.WaitForExitAsync(deadline.Token);
                if (child.ExitCode != 0) throw new IOException("The source worker failed after its terminal record.");
            }
            return chunk;
        }
        catch { RequestCancel(); throw; }
    }
    private async Task DrainError()
    {
        // Diagnostics never accumulate or enter public receipts. The child has
        // a separate private stderr channel, and must not block on its pipe.
        var buffer = new char[1024];
        try { while (await child.StandardError.ReadAsync(buffer, lifetime.Token) != 0) { } }
        catch (Exception error) when (error is IOException or OperationCanceledException or ObjectDisposedException) { }
    }
    public void RequestCancel()
    {
        lock (shutdownGate)
        {
            if (disposed != 0) return;
            if (Interlocked.Exchange(ref cancelled, 1) == 0)
            {
                lifetime.Cancel();
                try { child.StandardOutput.Close(); }
                catch (Exception error) when (error is IOException or ObjectDisposedException or InvalidOperationException) { }
            }
            // Retry termination if an earlier attempt raced device/process
            // teardown or the OS refused it. Cancellation callbacks never throw.
            try { if (!child.HasExited) child.Kill(entireProcessTree: true); }
            catch (Exception error) when (error is Win32Exception or InvalidOperationException or ObjectDisposedException)
            { terminationError = error; }
        }
    }
    public async ValueTask DisposeAsync()
    {
        await disposeGate.WaitAsync();
        try
        {
            if (disposed != 0) return;
            RequestCancel();
            for (var attempt = 0; attempt < 2; attempt++)
            {
                using var grace = new CancellationTokenSource(TimeSpan.FromSeconds(5));
                try { await child.WaitForExitAsync(grace.Token); break; }
                catch (OperationCanceledException) when (attempt == 0) { RequestCancel(); }
                catch (OperationCanceledException error)
                {
                    throw new IOException("The source worker did not terminate within its cancellation deadline.", terminationError ?? error);
                }
            }
            await stderrDrain;
            lock (shutdownGate)
            {
                reader.Dispose(); child.Dispose(); lifetime.Dispose(); disposed = 1;
            }
        }
        finally { disposeGate.Release(); }
    }
}
