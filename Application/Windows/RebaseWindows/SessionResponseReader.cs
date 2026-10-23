using System.Text;

namespace Rebase.Windows;

public static class SessionResponseReader
{
    public const int MaximumBytes = 16 * 1024 * 1024;
    public static async Task<string> Read(Stream stream, CancellationToken cancellation)
    {
        using var collected = new MemoryStream();
        var buffer = new byte[8192];
        while (true)
        {
            var count = await stream.ReadAsync(buffer.AsMemory(), cancellation);
            if (count == 0) throw new IOException("The shared session closed before replying.");
            var newline = Array.IndexOf(buffer, (byte)10, 0, count);
            var payload = newline >= 0 ? newline : count;
            if (collected.Length + payload > MaximumBytes) throw new InvalidDataException("The session response exceeds 16 MiB.");
            collected.Write(buffer, 0, payload);
            if (newline < 0) continue;
            if (newline != count - 1) throw new InvalidDataException("The session emitted unexpected data after its reply.");
            return new UTF8Encoding(false, true).GetString(collected.GetBuffer(), 0, (int)collected.Length);
        }
    }
}
