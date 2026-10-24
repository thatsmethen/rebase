using Rebase.Windows;
using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

var checks = 0;
void Check(bool good) { ++checks; if (!good) throw new Exception("Control " + checks + " failed."); }
void Reject(Action action) { ++checks; try { action(); } catch (InvalidDataException) { return; } throw new Exception("Expected rejection " + checks); }
var response = ProtocolJson.Decode("{\"protocol\":1,\"id\":7,\"ok\":true,\"state\":{\"revision\":5,\"dirty\":true,\"needsSaveAs\":true,\"selection\":{\"trackID\":\"t\",\"clipID\":\"c\"},\"canUndo\":true}}", 7);
Check(response.State!.Revision == 5 && response.State.Selection.ClipID == "c" && response.State.NeedsSaveAs);
Reject(() => ProtocolJson.Decode("{\"protocol\":2,\"id\":7,\"ok\":true,\"state\":{}}", 7));
Reject(() => ProtocolJson.Decode("{\"protocol\":1,\"id\":6,\"ok\":true,\"state\":{}}", 7));
Reject(() => ProtocolJson.Decode("{\"protocol\":1,\"id\":7,\"ok\":true}", 7));
var request = JsonSerializer.Serialize(new SessionRequest { Command = "moveClip", ClipID = "clip", ExpectedRevision = 42, Id = 9, Value = 2, Snap = "quarter" }, ProtocolJson.Options);
using (var json = JsonDocument.Parse(request))
{
    Check(json.RootElement.GetProperty("clipID").GetString() == "clip");
    Check(json.RootElement.GetProperty("expectedRevision").GetUInt64() == 42);
    Check(!json.RootElement.TryGetProperty("path", out _));
}
var bytes = new byte[60]; // 44-byte canonical header plus two stereo float frames.
Encoding.ASCII.GetBytes("RIFF").CopyTo(bytes, 0); BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(4), 52);
Encoding.ASCII.GetBytes("WAVEfmt ").CopyTo(bytes, 8); BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(16), 16);
BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(20), 3); BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(22), 2);
BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(24), 48000); BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(28), 384000);
BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(32), 8); BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(34), 32);
Encoding.ASCII.GetBytes("data").CopyTo(bytes, 36); BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(40), 16);
BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(44), BitConverter.SingleToInt32Bits(0.25f));
BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(48), BitConverter.SingleToInt32Bits(-0.5f));
var pcm = SnapshotReader.Decode(bytes, 48000, 2);
Check(pcm.Frames == 2 && pcm.SampleRate == 48000 && pcm.Samples.SequenceEqual(new[] { 0.25f, -0.5f, 0, 0 }));
Reject(() => SnapshotReader.Decode(bytes, 44100, 2));
Reject(() => SnapshotReader.Decode(bytes, 48000, 3));
Reject(() => SnapshotReader.Decode(bytes[..^1], 48000, 2));
var corrupt = (byte[])bytes.Clone(); BinaryPrimitives.WriteInt32LittleEndian(corrupt.AsSpan(44), BitConverter.SingleToInt32Bits(float.NaN));
Reject(() => SnapshotReader.Decode(corrupt, 48000, 2));
corrupt = (byte[])bytes.Clone(); BinaryPrimitives.WriteUInt16LittleEndian(corrupt.AsSpan(22), 1);
Reject(() => SnapshotReader.Decode(corrupt, 48000, 2));
var path = Path.Combine(Path.GetTempPath(), "rebase-snapshot-control-" + Guid.NewGuid().ToString("N") + ".wav");
try
{
    File.WriteAllBytes(path, bytes);
    var info = new RenderSnapshot { Kind = "project", Path = path, Revision = 17, SampleRate = 48000, Frames = 2, Channels = 2, WavBytes = 60, Sha256 = Convert.ToHexString(SHA256.HashData(bytes)) };
    Check(SnapshotReader.Read(info, path, 17).Samples[1] == -0.5f);
    Reject(() => SnapshotReader.Read(info, path, 18));
    Reject(() => SnapshotReader.Read(info, path + ".other", 17));
    info.Sha256 = new string('0', 64); Reject(() => SnapshotReader.Read(info, path, 17));
    info.WavBytes = 59; Reject(() => SnapshotReader.Read(info, path, 17));
}
finally { File.Delete(path); }
async Task RejectFrame(byte[] input)
{
    ++checks;
    try { _ = await SessionResponseReader.Read(new MemoryStream(input), CancellationToken.None); }
    catch (Exception error) when (error is IOException or InvalidDataException or DecoderFallbackException) { return; }
    throw new Exception("Expected framing rejection");
}
Check(await SessionResponseReader.Read(new MemoryStream(Encoding.UTF8.GetBytes("hello\n")), CancellationToken.None) == "hello");
await RejectFrame(Encoding.UTF8.GetBytes("partial"));
await RejectFrame(Encoding.UTF8.GetBytes("reply\nunsolicited"));
await RejectFrame([0xff, 0x0a]);
await RejectFrame(Enumerable.Repeat((byte)'a', SessionResponseReader.MaximumBytes + 1).ToArray());
using (var cancel = new CancellationTokenSource())
{
    cancel.Cancel(); ++checks;
    try { _ = await SessionResponseReader.Read(new MemoryStream(Encoding.UTF8.GetBytes("reply\n")), cancel.Token); throw new Exception("Expected cancellation"); }
    catch (OperationCanceledException) { }
}
checks += await SourceAuditionControls.Run();
checks += await WaveformControls.Run();
checks += await RulerControls.Run();
checks += await CPRReviewControls.Run();
checks += await AutomationControls.Run();
checks += await PlaybackRateControls.Run();
Console.WriteLine(JsonSerializer.Serialize(new { schema = 1, suite = "windows-host-portable-controls", checks, failures = 0, wpf_runtime_tested = false, playback_tested = false }));
