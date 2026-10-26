using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rebase.Windows;

// Authored wire/parser controls; these do not run Swift or a device.
static class SourceStreamControls
{
    internal const string EventID = "00000000-0000-4000-8000-000000000091";
    internal static ProjectView Project() => JsonSerializer.Deserialize<ProjectView>($$$"""
        {"id":"stream-project","name":"Authored stream","sampleRate":48000,"tempoMap":{},"signatureMap":[],
         "tracks":[{"id":"stream-track","clips":[],"unresolvedAudioEvents":[{"id":"{{{EventID}}}","name":"Stream",
         "sourceSHA256":"{{{new string('a',64)}}}","event":{"identityOffset":100},"files":[{"object":{"identityOffset":1024}}]}]}],
         "cprMediaAttachments":[{"association":"user-selected","sourceSHA256":"{{{new string('a',64)}}}",
         "sourceFileIdentity":1024,"mediaSHA256":"{{{new string('b',64)}}}"}]}
        """, ProtocolJson.Options)!;
    public static async Task<int> Run()
    {
        int checks = 0;
        void Check(bool value) { checks++; if (!value) throw new Exception("Source stream control " + checks + " failed."); }
        async Task Reject(Func<Task> action)
        {
            checks++;
            try { await action(); }
            catch (Exception error) when (error is IOException or InvalidDataException or JsonException or OverflowException) { return; }
            throw new Exception("Malformed source stream accepted at " + checks);
        }
        var project = Project(); var selected = SourceEventView.Read(project).Single();
        var directory = Path.Combine(Path.GetTempPath(), "rebase-stream-controls-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(directory);
        try
        {
            var request = new SessionRequest { Command = "prepareSourceStream", Path = Path.Combine(directory,"control.ticket"), Mode = SourceAuditionMode.Original };
            var built = SourceStreamControlData.Build(project, selected, request, 7, 48000, 7);
            built.Ticket.Validate(request.Path, 7, selected, SourceAuditionMode.Original); Check(true);
            async Task Drain(byte[] bytes, SourceStreamTicket? ticket = null)
            {
                using var parser = new SourceStreamReader(new MemoryStream(bytes));
                await parser.Admit(ticket ?? built.Ticket, selected, project, CancellationToken.None);
                while (await parser.Read(CancellationToken.None) is not null) { }
                Check(parser.ReceivedFrames == (ticket ?? built.Ticket).Frames && parser.PCMHash is { Length:64 });
            }
            await Drain(built.Wire);
            // Independent IEEE words cross transport splits unchanged, including
            // signed zero and both signs of the smallest subnormal.
            var pcm = new byte[7 * 8];
            uint[] words = [0,0x80000000,1,0x80000001,0x3f800000,0xbf800000,0x3e800000];
            for (int i=0;i<14;i++) BinaryPrimitives.WriteUInt32LittleEndian(pcm.AsSpan(i*4),words[i%words.Length]);
            var split = SourceStreamControlData.Wire(built.Ticket,built.Proof,pcm,[1,2,1,3],[3,4]);
            using (var parser = new SourceStreamReader(new MemoryStream(split)))
            {
                await parser.Admit(built.Ticket,selected,project,CancellationToken.None); var received = new List<uint>();
                while(await parser.Read(CancellationToken.None) is { } chunk) received.AddRange(chunk.Samples.Select(BitConverter.SingleToUInt32Bits));
                Check(received.SequenceEqual(Enumerable.Range(0,14).Select(i=>words[i%words.Length])));
            }
            foreach(var change in new Action<byte[]>[] {
                bytes=>bytes[0]=0, bytes=>bytes[4]=2, bytes=>bytes[6]=5,
                bytes=>BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(8),8_388_609),
                bytes=>BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(12),524289) })
            { var bad=(byte[])built.Wire.Clone();change(bad);await Reject(()=>Drain(bad)); }
            foreach(var length in new[]{0,1,15,16,built.Wire.Length-1}) await Reject(()=>Drain(built.Wire[..length]));
            await Reject(()=>Drain([..built.Wire,0]));
            foreach(var mutate in new Action<JsonObject>[] {
                p=>p["generation"]=Guid.NewGuid().ToString(),p=>p["revision"]=8,p=>p["mode"]="nativeMode1ProjectRate",
                p=>p["channels"]=1,p=>p["frames"]=8,p=>p["sampleRate"]=44100,p=>p["maximumChunkFrames"]=0,
                p=>p["proofSHA256"]=new string('0',64),p=>p["proof"]!["currentProjectSHA256"]="invalid" })
            { var records=SourceStreamControlData.Records(built.Wire); mutate(records[0].Meta); await Reject(()=>Drain(SourceStreamControlData.Encode(records))); }
            foreach(var mutate in new Action<JsonObject>[] {
                p=>p["generation"]=Guid.NewGuid().ToString(),p=>p["sequence"]=1,p=>p["absoluteFrame"]=1,
                p=>p["frames"]=0,p=>p["frames"]=65537,p=>p["logicalBlock"]=1,p=>p["logicalOffset"]=1,
                p=>p["logicalFrames"]=6,p=>p["sha256"]=new string('0',64) })
            { var records=SourceStreamControlData.Records(built.Wire);mutate(records[1].Meta);await Reject(()=>Drain(SourceStreamControlData.Encode(records))); }
            foreach(var mutate in new Action<JsonObject>[] {
                p=>p["generation"]=Guid.NewGuid().ToString(),p=>p["nextSequence"]=0,p=>p["nextAbsoluteFrame"]=6,
                p=>p["frames"]=6,p=>p["pcmSHA256"]=new string('0',64) })
            { var records=SourceStreamControlData.Records(built.Wire);mutate(records[^1].Meta);await Reject(()=>Drain(SourceStreamControlData.Encode(records))); }
            foreach(var bits in new uint[]{0x7f800000,0xff800000,0x7fc00001})
            {
                var bad=(byte[])pcm.Clone(); BinaryPrimitives.WriteUInt32LittleEndian(bad,bits);
                await Reject(()=>Drain(SourceStreamControlData.Wire(built.Ticket,built.Proof,bad,[7],[7])));
            }
            var changed=SourceStreamControlData.Records(split);changed[2].Meta["logicalFrames"]=4;
            await Reject(()=>Drain(SourceStreamControlData.Encode(changed)));
            var missing=SourceStreamControlData.Records(built.Wire);missing.RemoveAt(missing.Count-1);
            await Reject(()=>Drain(SourceStreamControlData.Encode(missing)));
            var duplicate=SourceStreamControlData.Records(built.Wire);duplicate[1].Meta["SEQUENCE"]=0;
            await Reject(()=>Drain(SourceStreamControlData.Encode(duplicate)));
            var fail=SourceStreamControlData.Records(built.Wire);fail.RemoveRange(1,2);fail.Add(new(4,new JsonObject {
                ["generation"]=built.Ticket.Generation,["code"]="producer",["message"]="Authored failure.",["lastAbsoluteFrame"]=0},[]));
            await Reject(()=>Drain(SourceStreamControlData.Encode(fail)));
            var eofRequest=new SessionRequest { Command=request.Command,Path=request.Path,Mode=request.Mode,StartSeconds=100 };
            var eof=SourceStreamControlData.Build(project,selected,eofRequest,7,48000,7); await Drain(eof.Wire,eof.Ticket);
            // A long admitted timeline may seek near its end without any huge
            // managed allocation. No 32-million-frame snapshot gate applies.
            var longRequest=new SessionRequest {Command=request.Command,Path=request.Path,Mode="nativeTimelineSourceRate",StartSeconds=86399.9999};
            var longSource=SourceStreamControlData.Build(project,selected,longRequest,7,48000,4_147_200_000);
            longSource.Ticket.Validate(request.Path,7,selected,longRequest.Mode); await Drain(longSource.Wire,longSource.Ticket);
            Check(longSource.Wire.Length<8192 && longSource.Ticket.TotalFrames>uint.MaxValue/2);
            using var wait=new CancellationTokenSource(); using var blocked=new SourceStreamReader(new BlockingReadStream());
            var pending=blocked.Admit(built.Ticket,selected,project,wait.Token);wait.Cancel();
            try {await pending;throw new Exception("Blocked read ignored cancellation.");}catch(OperationCanceledException){Check(true);}
        }
        finally { Directory.Delete(directory,true); }
        return checks;
    }
    private sealed class BlockingReadStream : Stream
    {
        public override async ValueTask<int> ReadAsync(Memory<byte> buffer,CancellationToken cancellationToken=default)
        {await Task.Delay(Timeout.Infinite,cancellationToken);return 0;}
        public override bool CanRead=>true;public override bool CanSeek=>false;public override bool CanWrite=>false;
        public override long Length=>throw new NotSupportedException();public override long Position{get=>0;set=>throw new NotSupportedException();}
        public override void Flush()=>throw new NotSupportedException();public override int Read(byte[] b,int o,int c)=>throw new NotSupportedException();
        public override long Seek(long o,SeekOrigin origin)=>throw new NotSupportedException();public override void SetLength(long n)=>throw new NotSupportedException();public override void Write(byte[] b,int o,int c)=>throw new NotSupportedException();
    }
}

static class SourceStreamControlData
{
    public sealed record Record(ushort Kind, JsonObject Meta, byte[] Payload);
    public sealed record Built(SourceStreamTicket Ticket, JsonObject Proof, byte[] Wire);
    public static readonly Factory Streams=new();
    public static Built Build(ProjectView project,SourceEventView selected,SessionRequest request,ulong revision,uint rate,ulong total,
        string? mediaHash=null,double sourceRate=0)
    {
        // Reuse the independent authored provenance fixture, then remove export
        // fields. Only tiny suffix PCM is allocated, even for long timelines.
        var start=(ulong)Math.Clamp(Math.Round((request.StartSeconds??0)*rate,MidpointRounding.AwayFromZero),0,total);
        if(start==total&&request.RewindAtEnd==true)start=0;
        if(total-start>65536)throw new InvalidOperationException("Authored stream control must use a bounded suffix.");
        var authored=new SessionRequest {Command="renderSourceEvent",Path=request.Path+".authored.wav",Mode=request.Mode};
        var render=SourceControlData.Render(project,selected,authored,revision,rate,Math.Max(1,total-start),mediaHash,sourceRate);
        var proof=JsonNode.Parse(File.ReadAllBytes(render.ManifestPath!))!.AsObject();SourceControlData.Delete(render.Path);
        foreach(var key in new[]{"wavFileName","wavBytes","wavSHA256","maximumFrames"})proof.Remove(key);
        proof["schema"]="rebase.source-stream-proof.v1";proof["startFrame"]=start;proof["totalFrames"]=total;proof["frames"]=total-start;
        var bytes=Encoding.UTF8.GetBytes(proof.ToJsonString());
        var ticket=new SourceStreamTicket {Generation=Guid.NewGuid().ToString(),Capability=Guid.NewGuid().ToString(),Revision=revision,
            EventID=selected.Id,Mode=request.Mode??SourceAuditionMode.Original,TicketPath=request.Path!,TicketSHA256=new('e',64),
            ProofSHA256=Convert.ToHexStringLower(SHA256.HashData(bytes)),SampleRate=rate,StartFrame=start,TotalFrames=total,Frames=total-start,MaximumChunkFrames=65536};
        var pcm=SourceControlData.Wave(rate,total-start,start)[58..];
        var wire=Wire(ticket,proof,pcm,pcm.Length==0?[]:[(uint)(total-start)],pcm.Length==0?[]:[total-start]);
        var built=new Built(ticket,proof,wire);Streams.Pending[ticket.Generation]=built;return built;
    }
    public static byte[] Wire(SourceStreamTicket t,JsonObject proof,byte[] pcm,uint[] chunks,ulong[] logicalLengths)
    {
        var records=new List<Record> {new(1,new JsonObject { ["schema"]="rebase.source-stream-admission.v1",["generation"]=t.Generation,
            ["revision"]=t.Revision,["eventID"]=t.EventID,["mode"]=t.Mode,["sampleRate"]=t.SampleRate,["startFrame"]=t.StartFrame,
            ["totalFrames"]=t.TotalFrames,["frames"]=t.Frames,["channels"]=2,["maximumChunkFrames"]=65536,
            ["proofSHA256"]=t.ProofSHA256,["proof"]=proof.DeepClone()},[])};
        ulong sequence=0,absolute=t.StartFrame,block=0,offset=0;int byteOffset=0;
        foreach(var frames in chunks)
        {
            var payload=pcm.AsSpan(byteOffset,(int)frames*8).ToArray();
            records.Add(new(2,new JsonObject{["generation"]=t.Generation,["sequence"]=sequence++,["absoluteFrame"]=absolute,["frames"]=frames,
                ["logicalBlock"]=block,["logicalOffset"]=offset,["logicalFrames"]=logicalLengths[block],
                ["sha256"]=Convert.ToHexStringLower(SHA256.HashData(payload))},payload));
            absolute+=frames;offset+=frames;byteOffset+=payload.Length;if(offset==logicalLengths[block]){block++;offset=0;}
        }
        records.Add(new(3,new JsonObject { ["generation"]=t.Generation,["nextSequence"]=sequence,["nextAbsoluteFrame"]=absolute,
            ["frames"]=t.Frames,["pcmSHA256"]=Convert.ToHexStringLower(SHA256.HashData(pcm))},[]));
        return Encode(records);
    }
    public static byte[] Encode(IEnumerable<Record> records)
    {
        using var output=new MemoryStream();
        foreach(var r in records){var meta=Encoding.UTF8.GetBytes(r.Meta.ToJsonString());byte[] h=[82,66,65,83,1,0,0,0,0,0,0,0,0,0,0,0];
            BinaryPrimitives.WriteUInt16LittleEndian(h.AsSpan(6),r.Kind);BinaryPrimitives.WriteUInt32LittleEndian(h.AsSpan(8),(uint)meta.Length);
            BinaryPrimitives.WriteUInt32LittleEndian(h.AsSpan(12),(uint)r.Payload.Length);output.Write(h);output.Write(meta);output.Write(r.Payload);}
        return output.ToArray();
    }
    public static List<Record> Records(byte[] wire)
    {
        var result=new List<Record>();int offset=0;
        while(offset<wire.Length){var h=wire.AsSpan(offset,16);int meta=(int)BinaryPrimitives.ReadUInt32LittleEndian(h[8..]),payload=(int)BinaryPrimitives.ReadUInt32LittleEndian(h[12..]);
            result.Add(new(BinaryPrimitives.ReadUInt16LittleEndian(h[6..]),JsonNode.Parse(wire.AsSpan(offset+16,meta))!.AsObject(),wire.AsSpan(offset+16+meta,payload).ToArray()));offset+=16+meta+payload;}
        return result;
    }
    public sealed class Factory : ISourceStreamFactory
    {
        public Dictionary<string,Built> Pending {get;}=[];
        public async Task<ISourceStream> Open(SourceStreamTicket ticket,SourceEventView selected,ProjectView project,CancellationToken cancellation)
        {
            var built=Pending[ticket.Generation];Pending.Remove(ticket.Generation);var reader=new SourceStreamReader(new MemoryStream(built.Wire));
            try{return new Worker(reader,await reader.Admit(ticket,selected,project,cancellation));}catch{reader.Dispose();throw;}
        }
    }
    private sealed class Worker(SourceStreamReader reader,SourceStreamAdmission admission) : ISourceStream
    {
        public SourceStreamAdmission Admission=>admission;
        public Task<SourceStreamChunk?> Read(CancellationToken cancellation)=>reader.Read(cancellation);
        public void RequestCancel(){}
        public ValueTask DisposeAsync(){reader.Dispose();return ValueTask.CompletedTask;}
    }
}
