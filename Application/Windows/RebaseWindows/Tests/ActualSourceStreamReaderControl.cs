using System.Buffers.Binary;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using Rebase.Windows;

// Optional production-helper integration probe. Unlike authored host controls,
// this executes the supplied built Rebase helper and the real process reader.
// It never creates a native device or exports a WAV.
static class ActualSourceStreamReaderControl
{
    public static async Task Run(string helper, string fixtureRoot, string output)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
        var scratch=Path.Combine(Path.GetDirectoryName(Path.GetFullPath(output))!,"reader-work");Directory.CreateDirectory(scratch);
        var start=new ProcessStartInfo(Path.GetFullPath(helper)){UseShellExecute=false,RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true};
        start.ArgumentList.Add("--stdio");using var child=Process.Start(start)??throw new Exception("Helper did not start.");
        child.StandardInput.NewLine="\n";
        var stderr=child.StandardError.ReadToEndAsync();
        using var deadline=new CancellationTokenSource(TimeSpan.FromSeconds(120));
        ulong next=0;SessionState state=new();var records=new List<object>();int checks=0;
        async Task<SessionResponse> Send(SessionRequest request)
        {
            request.Id=++next;request.ExpectedRevision=state.Revision;
            await child.StandardInput.WriteLineAsync(JsonSerializer.Serialize(request,ProtocolJson.Options));await child.StandardInput.FlushAsync();
            var response=ProtocolJson.Decode(await SessionResponseReader.Read(child.StandardOutput.BaseStream,deadline.Token),request.Id);
            if(!response.Ok)throw new Exception(response.Error?.Message);state=response.State!;return response;
        }
        void Check(bool value){checks++;if(!value)throw new Exception("Actual source reader check "+checks+" failed.");}
        try
        {
            using var expected=JsonDocument.Parse(await File.ReadAllBytesAsync(Path.Combine(fixtureRoot,"expected.json"),deadline.Token));
            var factory=new SourceStreamProcessFactory(Path.GetFullPath(helper));
            foreach(var row in expected.RootElement.GetProperty("cases").EnumerateArray())
            {
                // Explicit private copy keeps this probe independent of the
                // host Foundation temporary-directory policy. No fixture is edited.
                var original=Path.GetFullPath(Path.Combine(fixtureRoot,row.GetProperty("root").GetString()!));
                var copy=Path.Combine(scratch,Guid.NewGuid().ToString("N")+".rebaseproj");Directory.CreateDirectory(copy);
                foreach(var entry in Directory.EnumerateFileSystemEntries(original,"*",SearchOption.AllDirectories))
                {
                    var attrs=File.GetAttributes(entry);if(attrs.HasFlag(FileAttributes.ReparsePoint))throw new IOException("Fixture has a link.");
                    var destination=Path.Combine(copy,Path.GetRelativePath(original,entry));
                    if(attrs.HasFlag(FileAttributes.Directory))Directory.CreateDirectory(destination);else File.Copy(entry,destination);
                }
                await Send(new(){Command="open",Path=copy,AsCopy=false,DiscardChanges=true});
                var id=row.GetProperty("anchorID").GetString()!;await Send(new(){Command="selectClip",ClipID=id});
                var selected=SourceEventView.Read(state.Project).Single(e=>e.Id==id);
                var mode=row.GetProperty("modes").EnumerateArray().Single(m=>m.GetProperty("mode").GetString()==SourceAuditionMode.CompleteTrack);
                var rate=mode.GetProperty("sampleRate").GetUInt32();var total=mode.GetProperty("totalFrames").GetUInt64();
                var before=JsonSerializer.Serialize(state,ProtocolJson.Options);
                foreach(var point in new[]{"tail","eof","cancel"})
                {
                    ulong first=point=="tail"?total-1000:point=="eof"?total:0;
                    var ticketPath=Path.Combine(scratch,Guid.NewGuid().ToString("N")+".ticket");
                    var reply=await Send(new(){Command="prepareSourceStream",ClipID=id,Path=ticketPath,Mode=SourceAuditionMode.CompleteTrack,StartSeconds=(double)first/rate,RewindAtEnd=false});
                    var ticket=reply.SourceStream??throw new Exception("Missing stream ticket.");ticket.Validate(ticketPath,state.Revision,selected,SourceAuditionMode.CompleteTrack);
                    await using var worker=await factory.Open(ticket,selected,state.Project!,deadline.Token);
                    Check(ticket.StartFrame==first&&ticket.TotalFrames==total&&JsonSerializer.Serialize(state,ProtocolJson.Options)==before);
                    using var digest=IncrementalHash.CreateHash(HashAlgorithmName.SHA256);ulong frames=0;uint peak=0;
                    while(await worker.Read(deadline.Token) is { } chunk)
                    {
                        frames+=chunk.Frames;peak=Math.Max(peak,chunk.Frames);var bytes=new byte[chunk.Samples.Length*4];
                        for(int i=0;i<chunk.Samples.Length;i++)BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(i*4),BitConverter.SingleToUInt32Bits(chunk.Samples[i]));
                        digest.AppendData(bytes);
                        if(point=="cancel"){worker.RequestCancel();break;}
                    }
                    var hash=Convert.ToHexStringLower(digest.GetHashAndReset());
                    Check(point=="tail"?frames==1000&&hash==mode.GetProperty("tailPCMSHA256").GetString():point=="eof"?frames==0:frames is >0 and <=65536);
                    await worker.DisposeAsync();File.Delete(ticketPath);
                    records.Add(new{fixture=row.GetProperty("name").GetString(),point,first,total,frames,peak_payload_frames=peak,pcm_sha256=hash,worker_joined=true});
                }
            }
            var inspection=await Send(new(){Command="inspectSourceEvent",ClipID=state.Selection.ClipID});
            Check(inspection.SourceInspection is not null);
            await File.WriteAllTextAsync(output,JsonSerializer.Serialize(new{schema=1,suite="actual-shared-helper-managed-stream-reader",checks,failures=0,
                records,project_open="explicit-private-copy",device_playback_tested=false,wpf_runtime_tested=false,helper_responsive_after_cancellation=true},new JsonSerializerOptions{WriteIndented=true}));
        }
        finally
        {
            child.StandardInput.Close();using var grace=new CancellationTokenSource(TimeSpan.FromSeconds(3));
            try{await child.WaitForExitAsync(grace.Token);}catch(OperationCanceledException){child.Kill(entireProcessTree:true);await child.WaitForExitAsync();}
            await stderr;
        }
    }
}
