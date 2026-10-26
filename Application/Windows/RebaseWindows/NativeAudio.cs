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
[StructLayout(LayoutKind.Sequential)]
public struct AudioRateInfo
{
    public uint AbiVersion, SourceRate, EndpointRate, Converted;
    public ulong SourceFrames, EndpointFrames, EndpointPositionFrames, EndpointSubmittedFrames;
    public uint SoxrRecipe, Reserved;

    public readonly void ValidateForSource(LoadedSnapshot source)
    {
        if (source.SampleRate < 8000 || source.SampleRate > 192000 || source.Frames == 0 || source.Frames > 32_000_000)
            throw new InvalidDataException("The source exceeds the native transport format.");
        var maximum = (source.Frames * EndpointRate + source.SampleRate - 1) / source.SampleRate;
        if (AbiVersion != 1 || Reserved != 0 || SourceRate != source.SampleRate || SourceFrames != source.Frames ||
            EndpointRate < 8000 || EndpointRate > 192000 || EndpointFrames == 0 || EndpointFrames > 32_000_000 ||
            EndpointFrames > maximum || EndpointPositionFrames != 0 || EndpointSubmittedFrames != 0 ||
            Converted != (SourceRate == EndpointRate ? 0u : 1u) || SoxrRecipe != (Converted == 1 ? 6u : 0u) ||
            (Converted == 0 && EndpointFrames != SourceFrames))
            throw new InvalidDataException("The native rate-conversion receipt does not match this audio snapshot.");
    }
}
public sealed class NativeAudioException(int code, string message) : IOException(message)
{
    public int Code { get; } = code;
}
public interface IAudioOutput : IAsyncDisposable
{
    Task<DeviceFormat> Format();
    Task<AudioStatus> Status();
    Task<AudioRateInfo> RateInfo();
    Task SetSource(LoadedSnapshot source);
    Task Play();
    Task Pause();
    Task Stop();
    Task Seek(ulong frame);
}
public sealed partial class NativeAudio : IAudioOutput
{
    private sealed class AudioHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        public AudioHandle(IntPtr value) : base(true) { SetHandle(value); }
        protected override bool ReleaseHandle() { Api.Destroy(handle); return true; }
    }
    private static partial class Api
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
        [DllImport(Dll, EntryPoint = "rb_audio_rate_info", CallingConvention = CallingConvention.Cdecl)] public static extern int RateInfo(AudioHandle handle, out AudioRateInfo info);
    }
    static NativeAudio()
    {
        NativeLibrary.SetDllImportResolver(typeof(NativeAudio).Assembly, Resolve);
        if (Marshal.SizeOf<DeviceFormat>() != 12 || Marshal.SizeOf<AudioStatus>() != 72 || Marshal.SizeOf<AudioRateInfo>() != 56 || Marshal.SizeOf<AudioStreamDescriptor>() != 48 || Marshal.SizeOf<AudioStreamStatus>() != 160)
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
            4 => "The output must use Float32 stereo at a supported rate from 8000 to 192000 Hz.",
            5 => "The Windows audio device failed or changed. Prepare playback again.",
            6 => "There is not enough memory for this audio snapshot.",
            8 => "Playback stopped because the device clock outran submitted audio.",
            9 => "The endpoint-rate conversion failed. Prepare playback again.",
            10 => "The converted audio exceeds the supported playback snapshot size.",
            11 => "The audio converter requires the supported floating-point environment.",
            14 => "This source stream generation has been replaced.",
            15 => "The source stream violated the native producer protocol.",
            12 => "This source is too short to produce an output frame at the device rate.",
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
    internal static void ValidateSource(LoadedSnapshot? source)
    {
        if (source is null || source.Samples is null || source.SampleRate < 8000 || source.SampleRate > 192000 ||
            source.Frames == 0 || source.Frames > 32_000_000 || (ulong)source.Samples.LongLength != source.Frames * 2)
            throw new InvalidDataException("The native audio source must contain exactly two samples per frame at a supported rate.");
        foreach (var sample in source.Samples)
            if (!float.IsFinite(sample)) throw new InvalidDataException("The native audio source contains a nonfinite sample.");
    }
    public async Task SetSource(LoadedSnapshot source)
    {
        // Validate even independently constructed managed snapshots before any
        // native call can read their pinned memory. Keep the full sample scan
        // off the UI thread; native installation also validates its own copy.
        await Task.Run(() => ValidateSource(source));
        await Run(h =>
        {
            unsafe { fixed (float* samples = source.Samples) { Check(Api.Source(h, (IntPtr)samples, source.Frames, source.SampleRate)); } }
            return true;
        });
    }
    public Task<AudioRateInfo> RateInfo() => Run(h => { Check(Api.RateInfo(h, out var result)); return result; });
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
