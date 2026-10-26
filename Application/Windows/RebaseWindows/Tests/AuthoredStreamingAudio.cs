using Rebase.Windows;

// An explicitly authored adapter for the pre-existing small host lifecycle
// controls. It retains their fake device clocks/failures while adding stream
// admission/backpressure semantics. It does not exercise the native queue.
sealed class AuthoredStreamingAudio(IAudioOutput inner) : IAudioOutput, IAudioStreamOutput
{
    private AudioStreamDescriptor descriptor;
    private ulong accepted, sequence;
    private bool finished;
    public Task<DeviceFormat> Format()=>inner.Format();
    public Task<AudioStatus> Status()=>inner.Status();
    public Task<AudioRateInfo> RateInfo()=>inner.RateInfo();
    public Task SetSource(LoadedSnapshot source)=>inner.SetSource(source);
    public Task Play()=>inner.Play();public Task Pause()=>inner.Pause();public Task Stop()=>inner.Stop();public Task Seek(ulong frame)=>inner.Seek(frame);
    public ValueTask DisposeAsync()=>inner.DisposeAsync();
    public async Task BeginStream(AudioStreamDescriptor value)
    {
        descriptor=value;accepted=sequence=0;finished=false;
        if(value.SourceFrames>65536)throw new InvalidOperationException("Small authored adapter cannot simulate a long source.");
        await inner.SetSource(new(new float[(int)value.SourceFrames*2],value.SourceRate,value.SourceFrames));
    }
    public Task<bool> SubmitStream(ulong generation,ulong seq,ulong start,float[] samples,uint frames)
    {
        if(generation!=descriptor.Generation||seq!=sequence||start!=accepted||samples.Length!=frames*2)throw new InvalidDataException("Authored stream sequence mismatch.");
        accepted+=frames;sequence++;return Task.FromResult(true);
    }
    public Task FinishStream(ulong generation,ulong next,ulong frames)
    {
        if(generation!=descriptor.Generation||next!=sequence||frames!=accepted||frames!=descriptor.SourceFrames)throw new InvalidDataException("Authored stream EOF mismatch.");
        finished=true;return Task.CompletedTask;
    }
    public Task PlayStream(ulong generation)=>inner.Play();
    public Task PauseStream(ulong generation)=>inner.Pause();
    public Task CancelStream(ulong generation)=>inner.Stop();
    public async Task<AudioStreamStatus> StreamStatus(ulong generation)
    {
        var d=descriptor;var rate=await inner.RateInfo();var current=await inner.Status();
        return new(){AbiVersion=1,Phase=finished?current.Phase:6,Generation=d.Generation,SourceRate=rate.SourceRate,EndpointRate=rate.EndpointRate,
            SourceFrames=d.SourceFrames,SourceAccepted=accepted,SourceConsumed=accepted,SourcePosition=current.PositionFrames,
            EndpointProduced=finished?rate.EndpointFrames:0,EndpointSubmitted=finished?rate.EndpointFrames:0,
            EndpointPosition=finished?(current.PositionFrames==d.SourceFrames?rate.EndpointFrames:current.PositionFrames*rate.EndpointRate/d.SourceRate):0,
            EndpointTotal=finished?rate.EndpointFrames:0,SourceCapacity=d.SourceQueueFrames,EndpointCapacity=d.EndpointQueueFrames,
            Primed=finished?1u:0u,SourceEOF=finished?1u:0u,EndpointTotalFinal=finished?1u:0u,
            Converted=rate.Converted,SoxrRecipe=rate.SoxrRecipe,EndpointBufferFrames=128,PeakLeft=current.PeakLeft,PeakRight=current.PeakRight};
    }
}
