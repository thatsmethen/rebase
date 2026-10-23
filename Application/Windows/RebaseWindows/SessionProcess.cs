using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace Rebase.Windows;

public sealed class SessionProcess : IAsyncDisposable
{
    private readonly SemaphoreSlim gate = new(1, 1);
    private readonly CancellationTokenSource lifetime = new();
    private Process? process;
    private Task? stderrDrain;
    private ulong nextID;
    private string lastError = "";
    private bool disposed;
    private bool faulted;

    private void Start()
    {
        if (faulted) throw new IOException("The shared session stopped after a protocol failure. Reopen the application before continuing.");
        if (process is not null)
        {
            if (process.HasExited) throw new IOException("The shared session stopped. Reopen the application. " + lastError);
            return;
        }
        var executable = Path.Combine(AppContext.BaseDirectory, "rebase-session.exe");
        if (!File.Exists(executable)) throw new FileNotFoundException("The release is missing rebase-session.exe. Keep the complete application folder together.");
        var start = new ProcessStartInfo(executable)
        {
            UseShellExecute = false, CreateNoWindow = true,
            WorkingDirectory = AppContext.BaseDirectory,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardOutputEncoding = new UTF8Encoding(false), StandardErrorEncoding = new UTF8Encoding(false),
            StandardInputEncoding = new UTF8Encoding(false)
        };
        start.ArgumentList.Add("--stdio");
        process = Process.Start(start) ?? throw new IOException("Could not start the shared session.");
        process.StandardInput.NewLine = "\n";
        stderrDrain = DrainError(process);
    }
    private async Task DrainError(Process child)
    {
        var buffer = new char[1024];
        try
        {
            int count;
            while ((count = await child.StandardError.ReadAsync(buffer, lifetime.Token)) > 0)
            {
                var text = lastError + new string(buffer, 0, count);
                lastError = text.Length > 4096 ? text[^4096..] : text;
            }
        }
        catch (OperationCanceledException) { }
        catch (IOException) { }
    }
    public async Task<SessionResponse> Send(SessionRequest request)
    {
        await gate.WaitAsync(lifetime.Token);
        try
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            Start();
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(request.Command == "render" ? 120 : 60));
            using var cancellation = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token, deadline.Token);
            request.Id = checked(++nextID);
            var message = JsonSerializer.Serialize(request, ProtocolJson.Options);
            if (Encoding.UTF8.GetByteCount(message) > 65536) throw new InvalidDataException("The session request exceeds 64 KiB.");
            try
            {
                await process!.StandardInput.WriteLineAsync(message.AsMemory(), cancellation.Token);
                await process.StandardInput.FlushAsync(cancellation.Token);
                return ProtocolJson.Decode(await SessionResponseReader.Read(process.StandardOutput.BaseStream, cancellation.Token), request.Id);
            }
            catch (OperationCanceledException) when (!lifetime.IsCancellationRequested)
            {
                Terminate();
                throw new TimeoutException("The shared session did not reply in time and was stopped. Reopen the application before continuing.");
            }
            catch (Exception failure) when (failure is IOException or InvalidDataException or JsonException or DecoderFallbackException)
            {
                // No late/unread response may be mistaken for a later request.
                Terminate(); throw;
            }
        }
        finally { gate.Release(); }
    }
    private void Terminate()
    {
        faulted = true;
        if (process is null) return;
        try { if (!process.HasExited) process.Kill(entireProcessTree: true); }
        catch (InvalidOperationException) { }
    }
    public object[] ModuleReceipt() => process is null || process.HasExited ? [] : process.Modules.Cast<ProcessModule>()
        .Select(module => (object)new { name = module.ModuleName, path = module.FileName }).ToArray();
    public async ValueTask DisposeAsync()
    {
        if (disposed) return;
        disposed = true;
        lifetime.Cancel();
        // Normal close has drained UI work. EOF lets the helper release its
        // scratch copy. A stuck/in-flight helper is bounded by this short grace.
        if (process is not null)
        {
            try
            {
                process.StandardInput.Close();
                using var grace = new CancellationTokenSource(TimeSpan.FromSeconds(3));
                try { await process.WaitForExitAsync(grace.Token); }
                catch (OperationCanceledException) { if (!process.HasExited) process.Kill(entireProcessTree: true); }
            }
            catch (InvalidOperationException) { }
            catch (IOException) { Terminate(); }
            await process.WaitForExitAsync();
            if (stderrDrain is not null) await stderrDrain;
            process.Dispose();
        }
        lifetime.Dispose();
    }
}
