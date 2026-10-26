using System.Runtime.InteropServices;

namespace Rebase.Windows;

[StructLayout(LayoutKind.Sequential)]
public struct AudioStreamDescriptor
{
    public uint AbiVersion, SourceRate, Channels, MaxBlockFrames;
    public ulong Generation, SourceFrames;
    public uint SourceQueueFrames, EndpointQueueFrames, PrimeEndpointFrames, Reserved;
    public static AudioStreamDescriptor For(SourceStreamTicket ticket, ulong generation) => new()
    {
        AbiVersion = 1, SourceRate = ticket.SampleRate, Channels = 2, MaxBlockFrames = ticket.MaximumChunkFrames,
        Generation = generation, SourceFrames = ticket.Frames, SourceQueueFrames = 131072, EndpointQueueFrames = 131072,
        PrimeEndpointFrames = 0 // Native selects a measured device-buffer-safe threshold.
    };
    internal readonly void Validate()
    {
        if (AbiVersion != 1 || Reserved != 0 || Generation == 0 || SourceRate is < 8000 or > 192000 || Channels != 2 ||
            SourceFrames == 0 || MaxBlockFrames is 0 or > 65536 || SourceQueueFrames is < 4096 or > 262144 ||
            EndpointQueueFrames is < 4096 or > 262144 || MaxBlockFrames > SourceQueueFrames || PrimeEndpointFrames > EndpointQueueFrames)
            throw new InvalidDataException("The source stream descriptor exceeds its format or queue bounds.");
    }
}
[StructLayout(LayoutKind.Sequential)]
public struct AudioStreamStatus
{
    public uint AbiVersion, Phase, SourceRate, EndpointRate;
    public ulong Generation, SourceFrames, SourceAccepted, SourceConsumed, SourcePosition;
    public ulong EndpointProduced, EndpointSubmitted, EndpointPosition, EndpointTotal;
    public uint SourceQueued, EndpointQueued, SourceCapacity, EndpointCapacity, SourcePeak, EndpointPeak;
    public uint Primed, SourceEOF, EndpointTotalFinal, Converted;
    public int Result, HResult;
    public float PeakLeft, PeakRight;
    public uint EndpointBufferFrames, ClockApproximate, SoxrRecipe, Reserved;

    public readonly void Validate(AudioStreamDescriptor descriptor)
    {
        descriptor.Validate();
        var maximum = ((UInt128)descriptor.SourceFrames * EndpointRate + descriptor.SourceRate - 1) / descriptor.SourceRate;
        if (AbiVersion != 1 || Reserved != 0 || Generation != descriptor.Generation || SourceRate != descriptor.SourceRate ||
            SourceFrames != descriptor.SourceFrames || EndpointRate is < 8000 or > 192000 || Phase is < 1 or > 8 ||
            SourcePosition > SourceConsumed || SourceConsumed > SourceAccepted || SourceAccepted > SourceFrames ||
            EndpointPosition > EndpointSubmitted || EndpointSubmitted > EndpointProduced || (UInt128)EndpointProduced > maximum ||
            SourceQueued > SourceCapacity || EndpointQueued > EndpointCapacity || SourceCapacity != descriptor.SourceQueueFrames ||
            EndpointCapacity != descriptor.EndpointQueueFrames || SourcePeak > SourceCapacity || EndpointPeak > EndpointCapacity ||
            Primed > 1 || SourceEOF > 1 || EndpointTotalFinal > 1 || ClockApproximate > 1 ||
            Converted != (SourceRate == EndpointRate ? 0u : 1u) || SoxrRecipe != (Converted == 1 ? 6u : 0u) ||
            EndpointBufferFrames == 0 || EndpointBufferFrames > EndpointCapacity ||
            (EndpointTotalFinal == 0 && EndpointTotal != 0) ||
            (EndpointTotalFinal == 1 && (SourceEOF != 1 || SourceConsumed != SourceFrames || EndpointTotal != EndpointProduced)) ||
            (SourceEOF == 1 && SourceAccepted != SourceFrames) ||
            (Phase == 4 && (EndpointTotalFinal != 1 || EndpointPosition != EndpointTotal || SourcePosition != SourceFrames)) ||
            !float.IsFinite(PeakLeft) || !float.IsFinite(PeakRight))
            throw new InvalidDataException("The native stream status does not match its generation and bounded queues.");
        if (Phase == 5 || Result != 0) throw new NativeAudioException(Result, "The native source stream stopped (code " + Result + "). Prepare playback again.");
    }
    public readonly AudioRateInfo RateInfo => new()
    {
        AbiVersion = 1, SourceRate = SourceRate, EndpointRate = EndpointRate, Converted = Converted,
        SourceFrames = SourceFrames, EndpointFrames = EndpointTotalFinal == 1 ? EndpointTotal : 0,
        EndpointPositionFrames = EndpointPosition, EndpointSubmittedFrames = EndpointSubmitted, SoxrRecipe = SoxrRecipe
    };
}
public interface IAudioStreamOutput
{
    Task BeginStream(AudioStreamDescriptor descriptor);
    Task<bool> SubmitStream(ulong generation, ulong sequence, ulong startFrame, float[] samples, uint frames);
    Task FinishStream(ulong generation, ulong nextSequence, ulong committedFrames);
    Task PlayStream(ulong generation);
    Task PauseStream(ulong generation);
    Task CancelStream(ulong generation);
    Task<AudioStreamStatus> StreamStatus(ulong generation);
}

public sealed partial class NativeAudio : IAudioStreamOutput
{
    private static partial class Api
    {
        [DllImport(Dll, EntryPoint = "rb_audio_stream_begin", CallingConvention = CallingConvention.Cdecl)] public static extern int StreamBegin(AudioHandle handle, in AudioStreamDescriptor descriptor);
        [DllImport(Dll, EntryPoint = "rb_audio_stream_submit", CallingConvention = CallingConvention.Cdecl)] public static extern int StreamSubmit(AudioHandle handle, ulong generation, ulong sequence, ulong start, IntPtr samples, uint frames);
        [DllImport(Dll, EntryPoint = "rb_audio_stream_finish", CallingConvention = CallingConvention.Cdecl)] public static extern int StreamFinish(AudioHandle handle, ulong generation, ulong sequence, ulong frames);
        [DllImport(Dll, EntryPoint = "rb_audio_stream_play", CallingConvention = CallingConvention.Cdecl)] public static extern int StreamPlay(AudioHandle handle, ulong generation);
        [DllImport(Dll, EntryPoint = "rb_audio_stream_pause", CallingConvention = CallingConvention.Cdecl)] public static extern int StreamPause(AudioHandle handle, ulong generation);
        [DllImport(Dll, EntryPoint = "rb_audio_stream_cancel", CallingConvention = CallingConvention.Cdecl)] public static extern int StreamCancel(AudioHandle handle, ulong generation);
        [DllImport(Dll, EntryPoint = "rb_audio_stream_status", CallingConvention = CallingConvention.Cdecl)] public static extern int StreamStatus(AudioHandle handle, ulong generation, out AudioStreamStatus status);
    }
    public Task BeginStream(AudioStreamDescriptor descriptor)
    { descriptor.Validate(); return Run(h => { Check(Api.StreamBegin(h, in descriptor)); return true; }); }
    public Task<bool> SubmitStream(ulong generation, ulong sequence, ulong startFrame, float[] samples, uint frames)
    {
        if (generation == 0 || samples is null || frames is 0 or > 65536 || samples.LongLength != (long)frames * 2)
            throw new InvalidDataException("Invalid source stream block.");
        return Run(h =>
        {
            unsafe
            {
                fixed (float* pointer = samples)
                {
                    var result = Api.StreamSubmit(h, generation, sequence, startFrame, (IntPtr)pointer, frames);
                    if (result == 13) return false; // Explicit no-consumption backpressure.
                    Check(result); return true;
                }
            }
        });
    }
    public Task FinishStream(ulong generation, ulong nextSequence, ulong committedFrames) => Run(h => { Check(Api.StreamFinish(h, generation, nextSequence, committedFrames)); return true; });
    public Task PlayStream(ulong generation) => Run(h => { Check(Api.StreamPlay(h, generation)); return true; });
    public Task PauseStream(ulong generation) => Run(h => { Check(Api.StreamPause(h, generation)); return true; });
    public Task CancelStream(ulong generation) => Run(h => { Check(Api.StreamCancel(h, generation)); return true; });
    public Task<AudioStreamStatus> StreamStatus(ulong generation) => Run(h => { Check(Api.StreamStatus(h, generation, out var status)); return status; });
}
