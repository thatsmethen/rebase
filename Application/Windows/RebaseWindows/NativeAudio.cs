using Microsoft.Win32.SafeHandles;
using System.Reflection;
using System.Runtime.InteropServices;

namespace Rebase.Windows;

[StructLayout(LayoutKind.Sequential)]
public struct DeviceFormat { public uint SampleRate, Channels, Float32; }
[StructLayout(LayoutKind.Sequential)]
public struct AudioStatus
{
    public uint AbiVersion, Phase, SampleRate, EndpointBufferFrames;
    public ulong TotalFrames, PositionFrames, SubmittedFrames, Generation;
    public float PeakLeft, PeakRight;
    public int Result, HResult;
    public uint ClockReadingApproximate, Reserved;
}
public sealed class NativeAudioException(int code, string message) : IOException(message)
{
    public int Code { get; } = code;
}
public interface IAudioOutput : IAsyncDisposable
{
    Task<DeviceFormat> Format();
    Task<AudioStatus> Status();
    Task SetSource(LoadedSnapshot source);
    Task Play();
    Task Pause();
    Task Stop();
    Task Seek(ulong frame);
}
public sealed class NativeAudio : IAudioOutput
{
    private sealed class AudioHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        public AudioHandle(IntPtr value) : base(true) { SetHandle(value); }
        protected override bool ReleaseHandle() { Api.Destroy(handle); return true; }
    }
    private static class Api
    {
        private const string Dll = "RebaseWindowsAudio.dll";
        [DllImport(Dll, EntryPoint = "rb_audio_create", CallingConvention = CallingConvention.Cdecl)] public static extern int Create(out IntPtr handle);
        [DllImport(Dll, EntryPoint = "rb_audio_destroy", CallingConvention = CallingConvention.Cdecl)] public static extern void Destroy(IntPtr handle);
        [DllImport(Dll, EntryPoint = "rb_audio_default_format", CallingConvention = CallingConvention.Cdecl)] public static extern int Format(AudioHandle handle, out DeviceFormat format);
        [DllImport(Dll, EntryPoint = "rb_audio_set_source", CallingConvention = CallingConvention.Cdecl)] public static extern int Source(AudioHandle handle, IntPtr samples, ulong frames, uint rate);
        [DllImport(Dll, EntryPoint = "rb_audio_play", CallingConvention = CallingConvention.Cdecl)] public static extern int Play(AudioHandle handle);
        [DllImport(Dll, EntryPoint = "rb_audio_pause", CallingConvention = CallingConvention.Cdecl)] public static extern int Pause(AudioHandle handle);
        [DllImport(Dll, EntryPoint = "rb_audio_stop", CallingConvention = CallingConvention.Cdecl)] public static extern int Stop(AudioHandle handle);
        [DllImport(Dll, EntryPoint = "rb_audio_seek", CallingConvention = CallingConvention.Cdecl)] public static extern int Seek(AudioHandle handle, ulong frame);
        [DllImport(Dll, EntryPoint = "rb_audio_status", CallingConvention = CallingConvention.Cdecl)] public static extern int Status(AudioHandle handle, out AudioStatus status);
    }
    static NativeAudio()
    {
        NativeLibrary.SetDllImportResolver(typeof(NativeAudio).Assembly, Resolve);
        if (Marshal.SizeOf<DeviceFormat>() != 12 || Marshal.SizeOf<AudioStatus>() != 72)
            throw new InvalidOperationException("The native audio ABI layout does not match this build.");
    }
    private static IntPtr Resolve(string name, Assembly assembly, DllImportSearchPath? path) => name == "RebaseWindowsAudio.dll"
        ? NativeLibrary.Load(Path.Combine(AppContext.BaseDirectory, name)) : IntPtr.Zero;
    private readonly SemaphoreSlim gate = new(1, 1);
    private AudioHandle? handle;
    private bool disposed;
    private static void Check(int result)
    {
        if (result == 0) return;
        throw new NativeAudioException(result, result switch
        {
            1 => "The audio snapshot or transport position is invalid.",
            2 => "This transport operation is not available in the current state.",
            3 => "Windows has no default playback device. Connect or enable an output device and try again.",
            4 => "The output must use Float32 stereo at the project's exact sample rate. Device-rate conversion is not yet available.",
            5 => "The Windows audio device failed or changed. Prepare playback again.",
            6 => "There is not enough memory for this audio snapshot.",
            8 => "Playback stopped because the device clock outran submitted audio.",
            _ => "The native audio service stopped unexpectedly (code " + result + ")."
        });
    }
    private async Task<T> Run<T>(Func<AudioHandle, T> operation)
    {
        await gate.WaitAsync();
        try
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            return await Task.Run(() =>
            {
                if (handle is null) { Check(Api.Create(out var pointer)); handle = new AudioHandle(pointer); }
                return operation(handle);
            });
        }
        finally { gate.Release(); }
    }
    public Task<DeviceFormat> Format() => Run(h => { Check(Api.Format(h, out var result)); return result; });
    public Task<AudioStatus> Status() => Run(h =>
    {
        Check(Api.Status(h, out var result));
        if (result.AbiVersion != 1) throw new IOException("The native audio ABI version is unsupported.");
        if (result.Phase == 5) Check(result.Result);
        return result;
    });
    public Task SetSource(LoadedSnapshot source) => Run(h =>
    {
        unsafe { fixed (float* samples = source.Samples) { Check(Api.Source(h, (IntPtr)samples, source.Frames, source.SampleRate)); } }
        return true;
    });
    public Task Play() => Run(h => { Check(Api.Play(h)); return true; });
    public Task Pause() => Run(h => { Check(Api.Pause(h)); return true; });
    public Task Stop() => Run(h => { Check(Api.Stop(h)); return true; });
    public Task Seek(ulong frame) => Run(h => { Check(Api.Seek(h, frame)); return true; });
    public async ValueTask DisposeAsync()
    {
        await gate.WaitAsync();
        try { disposed = true; if (handle is not null) await Task.Run(handle.Dispose); handle = null; }
        finally { gate.Release(); }
    }
}
