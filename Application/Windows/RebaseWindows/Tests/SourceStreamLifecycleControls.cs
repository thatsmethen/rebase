using System.Text.Json;
using System.Text.Json.Nodes;
using System.Diagnostics;
using System.Reflection;
using Rebase.Windows;

// Authored lifecycle/queue controls. The bounded fake device never allocates a
// complete source and does not stand in for WASAPI or physical output evidence.
static class SourceStreamLifecycleControls
{
    public static async Task<int> Run()
    {
        int checks=0;
        void Check(bool condition) { checks++; if(!condition)throw new Exception("Stream lifecycle control "+checks+" failed."); }
        async Task Wait(Func<bool> done)
        {
            using var deadline=new CancellationTokenSource(TimeSpan.FromSeconds(5));
            while(!done())await Task.Delay(5,deadline.Token);
        }
        var client=new Client();var audio=new Device();var factory=new Factory();
        await using(var model=new StudioViewModel(client,audio,factory))
        {
            await model.Open("authored-stream",false,false);
            var unchanged=JsonSerializer.Serialize(model.State,ProtocolJson.Options);
            await model.AuditionSource("nativeTimelineSourceRate");await Wait(()=>audio.Accepted==1024);
            Check(model.IsPlaying && model.SourcePlaybackStatus is {SourceFrames:1_000_000_000} && audio.SnapshotCalls==0 && client.WavRequests==0);
            Check(audio.MaximumCopiedFrames==256 && factory.Workers[0].MaximumReadFrames==256 && audio.Accepted==1024);
            Check(JsonSerializer.Serialize(model.State,ProtocolJson.Options)==unchanged);
            audio.Position=512;audio.Phase=7;await model.Poll();Check(model.IsPlaying&&model.Position==512.0/48000);
            await model.Pause();Check(!model.IsPlaying&&audio.PauseCalls==1&&model.Position==512.0/48000);
            var oldGeneration=audio.Descriptor.Generation;await model.Play();await Wait(()=>audio.Accepted==1024);
            Check(model.IsPlaying&&client.Last!.StartSeconds==512.0/48000&&audio.Descriptor.Generation>oldGeneration);
            Check(factory.Workers[0].Cancelled&&factory.Workers[0].Disposed&&client.Requests==2);
            await model.Seek(123.25);await Wait(()=>audio.Accepted==1024);
            Check(model.IsPlaying&&model.Position==123.25&&client.Last!.StartSeconds==123.25&&audio.SnapshotCalls==0);
            audio.FailCancel=true;var before=model.Position;await model.Stop();
            Check(model.Position==before&&model.Status=="Authored cancellation barrier failure."&&model.IsPlaying);
            audio.FailCancel=false;
            audio.CancelBarrier=new(TaskCreationOptions.RunContinuationsAsynchronously);
            var stop=model.Stop();await Wait(()=>audio.CancelWaiting);
            Check(!stop.IsCompleted&&!factory.Workers[^1].Disposed);
            audio.CancelBarrier.SetResult();await stop;audio.CancelBarrier=null;
            Check(!model.IsPlaying&&model.Position==0&&factory.Workers[^1].Cancelled&&factory.Workers[^1].Disposed);
            var begins=audio.BeginCalls;await model.Seek(1_000_000_000.0/48000);
            Check(model.Position==1_000_000_000.0/48000&&audio.BeginCalls==begins&&model.Status.StartsWith("Finished",StringComparison.Ordinal));
            await model.Play();await Wait(()=>audio.Accepted==1024);Check(client.Last!.RewindAtEnd==true&&model.Position==0);
            // A stale poll cannot restore the replaced stream's clock.
            audio.DelayedStatus=new(TaskCreationOptions.RunContinuationsAsynchronously);var oldStatus=audio.Snapshot();var poll=model.Poll();
            await model.Seek(2);var current=model.Position;audio.DelayedStatus!.SetResult(oldStatus);audio.DelayedStatus=null;await poll;
            Check(model.Position==current&&current==2);
            await model.Stop();
            // Cancellation while the editing helper is issuing a ticket stops
            // the UI wait; its reply is later drained without killing the helper.
            client.Pending=new(TaskCreationOptions.RunContinuationsAsynchronously);
            var preparing=model.AuditionSource("nativeTimelineSourceRate");await Wait(()=>model.SourceStreamPreparing);
            begins=audio.BeginCalls;await model.Stop().WaitAsync(TimeSpan.FromSeconds(5));await preparing;
            Check(!model.Busy&&!model.SourceStreamPreparing&&audio.BeginCalls==begins&&!client.Disposed);
            client.Pending.SetResult(client.Reply(client.Last!));client.Pending=null;
            await model.Command("selectTrack",trackID:"stream-track");Check(!client.Disposed&&model.Status=="Selection updated.");
            Check(audio.SnapshotCalls==0&&client.WavRequests==0&&factory.Workers.All(worker=>worker.MaximumReadFrames<=256));
        }
        Check(client.Disposed&&factory.Workers.All(worker=>worker.Disposed));

        // Admission blocked on a pipe is cancelled independently from editing.
        client=new Client();audio=new Device();factory=new Factory{BlockAdmission=true};
        await using(var model=new StudioViewModel(client,audio,factory))
        {
            await model.Open("authored",false,false);var preparation=model.AuditionSource("nativeTimelineSourceRate");
            await Wait(()=>factory.OpenCalls==1);await model.Stop().WaitAsync(TimeSpan.FromSeconds(5));await preparation;
            Check(factory.AdmissionCancelled&&audio.BeginCalls==0&&!client.Disposed&&model.Status=="Stopped");
        }
        foreach(var stage in new[]{"prime","play","poll"})
        {
            client=new Client();audio=new Device();factory=new Factory();
            await using var model=new StudioViewModel(client,audio,factory);
            await model.Open("authored",false,false);
            audio.FailStatus=stage=="prime";audio.FailPlay=stage=="play";audio.FailCancel=stage!="poll";
            await model.AuditionSource("nativeTimelineSourceRate");
            if(stage=="poll") {audio.FailStatus=true;audio.FailCancel=true;await model.Poll();}
            Check(model.Status.Contains("could not be confirmed",StringComparison.Ordinal)&&audio.CancelCalls>0&&!factory.Workers[0].Disposed);
            var generation=audio.Descriptor.Generation;audio.FailCancel=false;audio.FailStatus=false;audio.FailPlay=false;
            await model.Stop();Check(model.Status=="Stopped"&&factory.Workers[0].Disposed&&audio.LastCancelled==generation);
            await model.Play();Check(model.IsPlaying&&audio.Descriptor.Generation>generation);
        }
        client=new Client();audio=new Device();factory=new Factory();
        await using(var model=new StudioViewModel(client,audio,factory))
        {
            await model.Open("authored",false,false);await model.AuditionSource("nativeTimelineSourceRate");
            audio.FailCancel=true;var notices=0;model.StateChanged+=()=>notices++;
            await model.Command("setGain",trackID:"stream-track",value:-3);
            Check(model.State.Revision==2&&model.State.Dirty&&model.NeedsSaveDecision&&model.SelectedTrack?.GainDB==-3&&notices==1);
            Check(model.Status.StartsWith("The project state was updated",StringComparison.Ordinal)&&!factory.Workers[0].Disposed);
            audio.FailCancel=false;await model.Stop();Check(model.Status=="Stopped"&&model.NeedsSaveDecision&&factory.Workers[0].Disposed);
        }
        // A producer failure cannot reach Finish or silently become device EOF.
        client=new Client();audio=new Device();factory=new Factory{FailRead=true};
        await using(var model=new StudioViewModel(client,audio,factory))
        {
            await model.Open("authored",false,false);await model.AuditionSource("nativeTimelineSourceRate");
            Check(!model.IsPlaying&&audio.FinishCalls==0&&factory.Workers[0].Disposed&&model.Status.Contains("Authored pipe truncation",StringComparison.Ordinal));
        }
        // Standalone status controls exercise 64-bit source totals and reject
        // impossible queue/clock/EOF claims before they reach the UI clock.
        var descriptor=new AudioStreamDescriptor{AbiVersion=1,SourceRate=192000,Channels=2,MaxBlockFrames=65536,Generation=99,
            SourceFrames=16_588_800_000,SourceQueueFrames=131072,EndpointQueueFrames=131072};
        var valid=new AudioStreamStatus{AbiVersion=1,Phase=2,SourceRate=192000,EndpointRate=48000,Generation=99,SourceFrames=descriptor.SourceFrames,
            SourceAccepted=1024,SourceConsumed=1024,SourcePosition=256,EndpointProduced=256,EndpointSubmitted=256,EndpointPosition=64,
            SourceCapacity=131072,EndpointCapacity=131072,Primed=1,Converted=1,SoxrRecipe=6,EndpointBufferFrames=128};
        valid.Validate(descriptor);Check(true);
        foreach(var mutation in new Func<AudioStreamStatus,AudioStreamStatus>[] {
            x=>{x.Generation++;return x;},x=>{x.SourceFrames=uint.MaxValue;return x;},x=>{x.SourcePosition=1025;return x;},
            x=>{x.SourceAccepted=x.SourceFrames+1;return x;},x=>{x.SourceConsumed=1025;return x;},x=>{x.EndpointPosition=257;return x;},
            x=>{x.EndpointTotal=256;return x;},x=>{x.EndpointTotalFinal=1;return x;},x=>{x.SourceEOF=1;return x;},
            x=>{x.SourceQueued=131073;return x;},x=>{x.EndpointPeak=131073;return x;},x=>{x.SourceCapacity--;return x;},
            x=>{x.Primed=2;return x;},x=>{x.SoxrRecipe=0;return x;},x=>{x.Converted=0;return x;},x=>{x.EndpointBufferFrames=0;return x;},
            x=>{x.Phase=4;return x;},x=>{x.PeakLeft=float.NaN;return x;},x=>{x.Reserved=1;return x;} })
        {
            checks++;try {mutation(valid).Validate(descriptor);throw new Exception("Invalid stream status accepted.");}catch(InvalidDataException){}
        }
        // Real child-process teardown with unread stdout, including repeated
        // cancellation racing disposal. No native endpoint or Swift process.
        var executable=Environment.ProcessPath??throw new InvalidOperationException("Control executable unavailable.");
        var start=new ProcessStartInfo(executable){UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true,RedirectStandardInput=true,CreateNoWindow=true};
        if(Path.GetFileNameWithoutExtension(executable).Equals("dotnet",StringComparison.OrdinalIgnoreCase))start.ArgumentList.Add(Assembly.GetExecutingAssembly().Location);
        start.ArgumentList.Add("--authored-unread-source-child");
        var child=Process.Start(start)??throw new Exception("Could not start authored child.");
        try { Check(await child.StandardError.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(5))=="authored-child-started"); }
        catch { if(!child.HasExited)child.Kill(entireProcessTree:true);await child.WaitForExitAsync();child.Dispose();throw; }
        var constructor=typeof(SourceStreamProcess).GetConstructor(BindingFlags.NonPublic|BindingFlags.Instance,null,[typeof(Process)],null)
            ??throw new Exception("Source process constructor unavailable.");
        var process=(SourceStreamProcess)constructor.Invoke([child]);
        var clock=Stopwatch.StartNew();
        await Task.WhenAll(Enumerable.Range(0,12).Select(_=>Task.Run(process.RequestCancel)).Append(process.DisposeAsync().AsTask()));
        Check(clock.Elapsed<TimeSpan.FromSeconds(5));
        process.RequestCancel();await process.DisposeAsync();Check(true);
        return checks;
    }
    private sealed class Client : ISessionClient
    {
        private readonly ProjectView project=SourceStreamControls.Project();
        public SessionRequest? Last;public int Requests,WavRequests;public bool Disposed;
        private ulong revision=1;private bool dirty;
        public TaskCompletionSource<SessionResponse>? Pending;
        public object[] ModuleReceipt()=>[];public ValueTask DisposeAsync(){Disposed=true;return ValueTask.CompletedTask;}
        public Task<SessionResponse> Send(SessionRequest request)
        {
            if(request.Command=="setGain") {revision++;dirty=true;project.Tracks[0].GainDB=request.Value!.Value;}
            if(request.Command=="renderSourceEvent")WavRequests++;
            if(request.Command=="prepareSourceStream") {Requests++;Last=request;if(Pending is not null)return Pending.Task;}
            return Task.FromResult(Reply(request));
        }
        public SessionResponse Reply(SessionRequest request)
        {
            var response=new SessionResponse{Protocol=1,Ok=true,State=new(){Revision=revision,Dirty=dirty,Project=project,Selection=new(){TrackID="stream-track",ClipID=SourceStreamControls.EventID}}};
            if(request.Command=="prepareSourceStream")
            {
                const ulong total=1_000_000_000;var start=(ulong)Math.Clamp(Math.Round((request.StartSeconds??0)*48000,MidpointRounding.AwayFromZero),0,total);
                if(start==total&&request.RewindAtEnd==true)start=0;
                response.SourceStream=new(){Generation=Guid.NewGuid().ToString(),Capability=Guid.NewGuid().ToString(),Revision=revision,
                    EventID=SourceStreamControls.EventID,Mode=request.Mode!,TicketPath=request.Path!,TicketSHA256=new('a',64),ProofSHA256=new('b',64),
                    SampleRate=48000,StartFrame=start,TotalFrames=total,Frames=total-start,MaximumChunkFrames=65536};
            }
            return response;
        }
    }
    private sealed class Factory : ISourceStreamFactory
    {
        public bool BlockAdmission,AdmissionCancelled,FailRead;public int OpenCalls;public List<Worker> Workers=[];
        public async Task<ISourceStream> Open(SourceStreamTicket ticket,SourceEventView selected,ProjectView project,CancellationToken cancellation)
        {
            OpenCalls++;
            if(BlockAdmission)try{await Task.Delay(Timeout.Infinite,cancellation);}catch(OperationCanceledException){AdmissionCancelled=true;throw;}
            var worker=new Worker(ticket){FailRead=FailRead};Workers.Add(worker);return worker;
        }
    }
    private sealed class Worker(SourceStreamTicket ticket) : ISourceStream
    {
        public bool Cancelled,Disposed,FailRead;public uint MaximumReadFrames;private ulong emitted,sequence;
        public SourceStreamAdmission Admission {get;}=new(ticket,65536,JsonSerializer.SerializeToElement(new{schema="authored-lifecycle-only"}));
        public Task<SourceStreamChunk?> Read(CancellationToken cancellation)
        {
            cancellation.ThrowIfCancellationRequested();if(FailRead)throw new EndOfStreamException("Authored pipe truncation.");
            if(emitted==ticket.Frames)return Task.FromResult<SourceStreamChunk?>(null);
            var count=(uint)Math.Min(256,ticket.Frames-emitted);MaximumReadFrames=Math.Max(count,MaximumReadFrames);
            var chunk=new SourceStreamChunk(sequence,ticket.StartFrame+emitted,count,sequence,0,count,new float[count*2]);
            sequence++;emitted+=count;return Task.FromResult<SourceStreamChunk?>(chunk);
        }
        public void RequestCancel()=>Cancelled=true;
        public ValueTask DisposeAsync(){Cancelled=Disposed=true;return ValueTask.CompletedTask;}
    }
    private sealed class Device : IAudioOutput,IAudioStreamOutput
    {
        public AudioStreamDescriptor Descriptor;public ulong Accepted,Position,LastCancelled;public uint Phase;
        public int SnapshotCalls,BeginCalls,PauseCalls,CancelCalls,FinishCalls;public uint MaximumCopiedFrames;
        public bool FailCancel,FailStatus,FailPlay,CancelWaiting;
        public TaskCompletionSource? CancelBarrier;
        public TaskCompletionSource<AudioStreamStatus>? DelayedStatus;private bool delayedTaken;
        public Task<DeviceFormat> Format()=>Task.FromResult(new DeviceFormat{SampleRate=48000,Channels=2,Float32=1});
        public Task SetSource(LoadedSnapshot source){SnapshotCalls++;throw new Exception("Streaming used full snapshot.");}
        public Task<AudioStatus> Status()=>throw new Exception("Streaming used snapshot status.");
        public Task<AudioRateInfo> RateInfo()=>throw new Exception("Streaming used snapshot rate info.");
        public Task Play()=>throw new Exception("Streaming used snapshot play.");public Task Pause()=>throw new Exception("Streaming used snapshot pause.");
        public Task Stop()=>throw new Exception("Streaming used snapshot stop.");public Task Seek(ulong frame)=>throw new Exception("Streaming used snapshot seek.");
        public ValueTask DisposeAsync()=>ValueTask.CompletedTask;
        public Task BeginStream(AudioStreamDescriptor value){Descriptor=value;BeginCalls++;Accepted=Position=0;Phase=6;return Task.CompletedTask;}
        public Task<bool> SubmitStream(ulong generation,ulong sequence,ulong start,float[] samples,uint frames)
        {
            if(generation!=Descriptor.Generation||start!=Accepted)throw new Exception("Foreign or noncontiguous fake producer.");
            if(Accepted>=1024)return Task.FromResult(false);
            MaximumCopiedFrames=Math.Max(MaximumCopiedFrames,frames);Accepted+=frames;return Task.FromResult(true);
        }
        public Task FinishStream(ulong generation,ulong nextSequence,ulong committedFrames){FinishCalls++;return Task.CompletedTask;}
        public Task PlayStream(ulong generation){if(FailPlay)throw new IOException("Authored Play failure.");Phase=2;return Task.CompletedTask;}
        public Task PauseStream(ulong generation){PauseCalls++;Phase=3;return Task.CompletedTask;}
        public async Task CancelStream(ulong generation)
        {
            CancelCalls++;if(FailCancel)throw new IOException("Authored cancellation barrier failure.");
            if(CancelBarrier is not null){CancelWaiting=true;await CancelBarrier.Task;CancelWaiting=false;}
            LastCancelled=generation;Phase=8;
        }
        public AudioStreamStatus Snapshot()=>new(){AbiVersion=1,Phase=Phase==6&&Accepted>=256?1u:Phase,SourceRate=48000,EndpointRate=48000,
            Generation=Descriptor.Generation,SourceFrames=Descriptor.SourceFrames,SourceAccepted=Accepted,SourceConsumed=Accepted,SourcePosition=Position,
            EndpointProduced=Accepted,EndpointSubmitted=Accepted,EndpointPosition=Position,SourceCapacity=Descriptor.SourceQueueFrames,
            EndpointCapacity=Descriptor.EndpointQueueFrames,SourcePeak=(uint)Accepted,EndpointPeak=(uint)Accepted,Primed=Accepted>=256?1u:0u,EndpointBufferFrames=128};
        public Task<AudioStreamStatus> StreamStatus(ulong generation)
        {
            if(FailStatus)throw new IOException("Authored native Status failure.");
            if(DelayedStatus is not null&&!delayedTaken){delayedTaken=true;return DelayedStatus.Task;}
            if(DelayedStatus is null)delayedTaken=false;
            return Task.FromResult(Snapshot());
        }
    }
}
