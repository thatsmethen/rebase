using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rebase.Windows;

static class ProjectStructureControls
{
    private const string ProjectID = "50c496f5-5de4-40e0-bc8c-2555d6cd1a26";
    private const string ReviewID = "8f258829-6b8a-41d4-b6a5-e36c3187ead2";
    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    private static string State(SessionState state) => JsonSerializer.Serialize(state, ProtocolJson.Options);
    private static JsonObject Report(bool large = false)
    {
        var hash = new string('a', 64);
        object Obj() => new { className = "MAudioTrackEvent", version = 1, declarationOffset = 20, objectOffset = 30, identityOffset = 40, payloadOffset = 50, payloadByteCount = 100, payloadSHA256 = hash };
        object Span() => new { offset = 50, byteCount = 100, sha256 = hash };
        return JsonSerializer.SerializeToNode(new {
            schemaVersion = 1, sourceSHA256 = hash, sourceByteCount = 1000,
            section = new { name = "Arrangement1", className = "PArrangement", rootOffset = 10, archiveOffset = 10, archiveByteCount = 990, archiveSHA256 = hash },
            arrangement = Obj(), root = Obj(), rootList = Obj(),
            lists = new[] { new { @object = Obj(), name = "Authored list", datumKind = 0, timingObjects = new object?[] { null }, childCount = 1 } },
            entries = new[] { new { path = new[] { 0 }, parentListIdentity = 40, token = Span(), @object = Obj(), repeatedIdentity = false, role = "track" } },
            tracks = new[] { new { track = Obj(), stateRepresentation = "inline", stateExtentKnown = true, state = Span(),
                volumeValue = new { encoding = "float64", floatingPointBits = "3ff0000000000000", finite = true, span = Span() },
                busCandidates = System.Array.Empty<object>(), savedDestinationCandidates = System.Array.Empty<object>(), unresolved = new[] { "Runtime routing unresolved" } } },
            resourceAssociations = new[] { new { track = Obj(), prefix = Span(), remainingTail = Span(), scope = "Saved association only" } },
            issues = new[] { new { code = "authored", detail = large ? new string('界', 30000) : "Authored structural control", span = Span() } }, nativeObjects = new[] { Obj() }
        })!.AsObject();
    }
    private static byte[] Bytes(JsonObject report) => Encoding.UTF8.GetBytes(report.ToJsonString(new() { WriteIndented = true, Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping }));
    private static ProjectStructurePage Page(byte[] bytes, int offset = 0) => new() {
        ReviewID = ReviewID, Revision = 1, ProjectID = ProjectID, ProjectManifestSHA256 = new string('b', 64), SourceSHA256 = new string('a', 64), SourceByteCount = 1000,
        ReportSHA256 = Hash(bytes), ReportByteCount = bytes.Length, Offset = offset,
        NextOffset = offset + ProjectStructurePage.ChunkBytes < bytes.Length ? offset + ProjectStructurePage.ChunkBytes : null,
        BytesBase64 = Convert.ToBase64String(bytes.AsSpan(offset, Math.Min(ProjectStructurePage.ChunkBytes, bytes.Length - offset)))
    };
    public static async Task<int> Run()
    {
        var count = 0;
        void Check(bool good) { count++; if (!good) throw new Exception("Saved structure host control " + count + " failed."); }
        void Reject(Action action) { count++; try { action(); } catch (Exception e) when (e is InvalidDataException or JsonException) { return; } throw new Exception("Expected structure rejection " + count); }
        var bytes = Bytes(Report()); var first = Page(bytes);
        var snapshot = ProjectStructureSnapshot.Decode(first, bytes);
        Check(snapshot.Hierarchy.Count == 1 && snapshot.Tracks.Count == 1 && snapshot.Issues.Count == 1 && snapshot.ListCount == 1 && snapshot.ObjectCount == 1);
        Check(snapshot.Json == Encoding.UTF8.GetString(bytes) && snapshot.Tracks[0].Contains("float64 3ff0000000000000") && !snapshot.Tracks[0].Contains("dB"));
        foreach (var mutate in new Action<ProjectStructurePage>[] {
            p=>p.ReviewID="bad",p=>p.ProjectID="bad",p=>p.SourceSHA256="bad",p=>p.ProjectManifestSHA256="bad",p=>p.ReportSHA256="bad",
            p=>p.SourceByteCount=0,p=>p.ReportByteCount=0,p=>p.ReportByteCount=ProjectStructurePage.MaximumReportBytes+1,
            p=>p.Offset=1,p=>p.Offset=-1,p=>p.NextOffset=1,p=>p.BytesBase64="invalid!",p=>p.BytesBase64+="\n",p=>p.BytesBase64=Convert.ToBase64String(bytes[..^1]) })
        { var p=Page(bytes); mutate(p); Reject(()=>p.Validate(0)); }
        var large = Bytes(Report(true)); Check(large.Length > ProjectStructurePage.ChunkBytes);
        var next = Page(large, ProjectStructurePage.ChunkBytes); next.ValidateContinuation(Page(large), ProjectStructurePage.ChunkBytes); count++;
        foreach (var mutate in new Action<ProjectStructurePage>[] { p=>p.ReviewID=Guid.NewGuid().ToString(),p=>p.Revision++,p=>p.ProjectID=Guid.NewGuid().ToString(),
            p=>p.SourceSHA256=new string('c',64),p=>p.ProjectManifestSHA256=new string('c',64),p=>p.ReportSHA256=new string('c',64),p=>p.SourceByteCount++ })
        { var p=Page(large,ProjectStructurePage.ChunkBytes);mutate(p);Reject(()=>p.ValidateContinuation(Page(large),ProjectStructurePage.ChunkBytes)); }
        Reject(()=>ProjectStructureSnapshot.Decode(first,bytes[..^1]));
        var changed=(byte[])bytes.Clone(); changed[^2]^=1; Reject(()=>ProjectStructureSnapshot.Decode(first,changed));
        var invalidUTF8=new byte[] {0xff};Reject(()=>ProjectStructureSnapshot.Decode(Page(invalidUTF8),invalidUTF8));
        foreach (var mutate in new Action<JsonObject>[] {
            r=>r["schemaVersion"]=2,r=>r["sourceSHA256"]=new string('c',64),r=>r["sourceByteCount"]=999,
            r=>r.Remove("entries"),r=>r["tracks"]=new JsonObject(),r=>r["issues"]=null,
            r=>r["entries"]![0]!["path"]=new JsonArray(-1),r=>r["entries"]![0]!["repeatedIdentity"]="false",
            r=>r["root"]!["payloadByteCount"]=1001,r=>r["root"]!["payloadSHA256"]="bad",
            r=>r["tracks"]![0]!["volumeValue"]!["integer"]="1",r=>r["tracks"]![0]!["unresolved"]=new JsonArray(1),
            r=>r["tracks"]![0]!["providerName"]=1,r=>r["tracks"]![0]!["providerIndex"]="1",r=>r["tracks"]![0]!["audioFlags"]=65536,
            r=>r["tracks"]![0]!["volumeValue"]!["floatingPointBits"]="bad",r=>r["tracks"]![0]!["volumeValue"]!["finite"]=false,
            r=>r["resourceAssociations"]![0]!["remainingTail"]!["offset"]=-1 })
        { var report=Report();mutate(report);var payload=Bytes(report);Reject(()=>ProjectStructureSnapshot.Decode(Page(payload),payload)); }
        var duplicate=Encoding.UTF8.GetBytes(Encoding.UTF8.GetString(bytes).Replace("\"schemaVersion\": 1", "\"schemaVersion\": 1, \"schemaVersion\": 1"));
        Reject(()=>ProjectStructureSnapshot.Decode(Page(duplicate),duplicate));
        var wire=JsonSerializer.SerializeToNode(new SessionResponse { Protocol=1,Id=7,Ok=true,State=new(),ProjectStructure=first },ProtocolJson.Options)!;
        Check(ProtocolJson.Decode(wire.ToJsonString(),7).ProjectStructure!.ReportSHA256==first.ReportSHA256);
        Reject(()=>ProtocolJson.Decode(wire.ToJsonString().Replace("\"reportByteCount\":", "\"REPORTBYTECOUNT\":1,\"reportByteCount\":"),7));
        wire["projectStructure"]!.AsObject().Remove("revision");Reject(()=>ProtocolJson.Decode(wire.ToJsonString(),7));

        var client=new Client(large);
        await using(var model=new StudioViewModel(client,new SilentAudio()))
        {
            await model.Open("authored.rebaseproj", false, false);var before=State(model.State);
            var result=await model.InspectProjectStructure();
            if(result is null) throw new Exception("Authored complete structure load failed: " + model.Status);
            Check(result?.Json==Encoding.UTF8.GetString(large) && State(model.State)==before);
            Check(client.Commands.SequenceEqual(new[]{"inspectProjectStructure"}.Concat(Enumerable.Repeat("projectStructurePage",(large.Length-1)/ProjectStructurePage.ChunkBytes)).Append("closeProjectStructure")));
            Check(client.Revisions.All(r=>r==1) && client.CloseCount==1);
        }
        foreach(var failure in new[]{"firstMalformed","continuationIdentity","continuationThrow","stateDrift","hash","close"})
        {
            client=new Client(large){Failure=failure};
            await using var model=new StudioViewModel(client,new SilentAudio());await model.Open("authored.rebaseproj", false, false);var before=State(model.State);
            Check(await model.InspectProjectStructure() is null && State(model.State)==before);
            Check(client.CloseCount==1 && client.Commands.Count(c=>c=="inspectProjectStructure")==1);
            Check(!string.IsNullOrWhiteSpace(model.Status));
        }
        // Pending read intent cannot silently inspect a different queued document.
        client=new Client(bytes);await using(var model=new StudioViewModel(client,new SilentAudio()))
        {
            await model.Open("authored.rebaseproj", false, false);var entered=new TaskCompletionSource();var release=new TaskCompletionSource();
            client.BeforeUndo=async()=>{entered.SetResult();await release.Task;};
            var undo=model.Command("undo");await entered.Task;var pending=model.InspectProjectStructure();release.SetResult();await undo;
            Check(await pending is null && client.Commands.Count==0 && model.State.Revision==2);
        }
        return count;
    }
    private sealed class Client(byte[] bytes) : ISessionClient
    {
        public string? Failure;public Func<Task>? BeforeUndo;public List<string> Commands=[];public List<ulong?> Revisions=[];public int CloseCount;
        private SessionState state=new(){Revision=1,Dirty=true,CanUndo=true,Project=new(){Id=ProjectID,Name="Authored",Tracks=[],
            TempoMap=JsonSerializer.SerializeToElement(new{}),SignatureMap=JsonSerializer.SerializeToElement(new{})},Selection=new(){TrackID="selected"}};
        public object[] ModuleReceipt()=>[];public ValueTask DisposeAsync()=>ValueTask.CompletedTask;
        public async Task<SessionResponse> Send(SessionRequest request)
        {
            if(request.Command=="undo"){if(BeforeUndo is not null)await BeforeUndo();state.Revision++;}
            var response=new SessionResponse{Protocol=1,Ok=true,State=JsonSerializer.Deserialize<SessionState>(State(state),ProtocolJson.Options)};
            if(request.Command is "inspectProjectStructure" or "projectStructurePage" or "closeProjectStructure")
            {
                Commands.Add(request.Command);Revisions.Add(request.ExpectedRevision);
                if(request.Command=="closeProjectStructure"){CloseCount++;if(Failure=="close")throw new IOException("Authored close failure.");return response;}
                if(request.Command=="projectStructurePage" && Failure=="continuationThrow")throw new IOException("Authored continuation failure.");
                response.ProjectStructure=Page(bytes,request.ReviewOffset??0);
                if(Failure=="firstMalformed")response.ProjectStructure.SourceByteCount=0;
                if(Failure=="continuationIdentity" && request.ReviewOffset>0)response.ProjectStructure.ProjectManifestSHA256=new string('c',64);
                if(Failure=="hash")response.ProjectStructure.ReportSHA256=new string('c',64);
                if(Failure=="stateDrift" && request.ReviewOffset>0)response.State!.Selection.ClipID="unexpected";
            }
            return response;
        }
    }
    private sealed class SilentAudio : IAudioOutput
    {
        public Task<DeviceFormat> Format()=>throw new Exception("Unexpected audio operation.");public Task SetSource(LoadedSnapshot s)=>throw new Exception("Unexpected audio operation.");
        public Task<AudioRateInfo> RateInfo()=>throw new Exception("Unexpected audio operation.");public Task<AudioStatus> Status()=>throw new Exception("Unexpected audio operation.");
        public Task Play()=>throw new Exception("Unexpected audio operation.");public Task Pause()=>throw new Exception("Unexpected audio operation.");public Task Seek(ulong f)=>throw new Exception("Unexpected audio operation.");
        public Task Stop()=>Task.CompletedTask;public ValueTask DisposeAsync()=>ValueTask.CompletedTask;
    }
    public static async Task Actual(string helper,string project,string output)
    {
        var start=new ProcessStartInfo(helper){UseShellExecute=false,RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true};start.ArgumentList.Add("--stdio");
        using var process=Process.Start(start)??throw new IOException("Unable to start helper.");process.StandardInput.NewLine="\n";
        var errors=process.StandardError.ReadToEndAsync();
        await using var client=new ActualClient(process);await using var model=new StudioViewModel(client,new SilentAudio());
        await model.Open(project, false, false);if(model.Project is null)throw new InvalidDataException(model.Status);
        var before=State(model.State);var report=await model.InspectProjectStructure()??throw new InvalidDataException(model.Status);
        if(State(model.State)!=before)throw new InvalidDataException("Actual read changed state.");
        var track=model.Project.Tracks.First();await model.Command("setGain",trackID:track.Id,value:-3);
        if(!model.State.Dirty)throw new InvalidDataException("Actual authored edit was not dirty: "+model.Status);
        var dirty=State(model.State);var after=await model.InspectProjectStructure()??throw new InvalidDataException(model.Status);
        if(State(model.State)!=dirty||after.Json!=report.Json)throw new InvalidDataException("Dirty inspection changed state or saved report.");
        await model.Command("undo");if(model.State.Dirty)throw new InvalidDataException("Inspection disrupted undo.");
        process.StandardInput.Close();await process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(10));if(process.ExitCode!=0)throw new IOException("Helper exit failed.");
        var record=new{schema="rebase.saved-structure-managed-helper-control.v1",status="passed",evidence_class="authored-package-and-actual-local-production-helper",helper_sha256=Hash(File.ReadAllBytes(helper)),report_sha256=report.ReportSHA256,source_sha256=report.SourceSHA256,report_bytes=report.ReportByteCount,hierarchy_entries=report.Hierarchy.Count,track_bindings=report.Tracks.Count,issues=report.Issues.Count,read_only=true,dirty_reopen_same_report=true,undo_preserved=true,commands=client.Commands,stderr_empty=(await errors).Length==0,native_window_tested=false};
        File.WriteAllText(output,JsonSerializer.Serialize(record,new JsonSerializerOptions{WriteIndented=true})+"\n");
        Console.WriteLine("Actual managed saved-structure helper journey passed.");
    }
    private sealed class ActualClient(Process process):ISessionClient
    {
        private ulong id;public List<string> Commands=[];public object[] ModuleReceipt()=>[];public ValueTask DisposeAsync()=>ValueTask.CompletedTask;
        public async Task<SessionResponse> Send(SessionRequest request)
        {
            request.Id=++id;Commands.Add(request.Command);await process.StandardInput.WriteLineAsync(JsonSerializer.Serialize(request,ProtocolJson.Options));await process.StandardInput.FlushAsync();
            using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(120));
            return ProtocolJson.Decode(await SessionResponseReader.Read(process.StandardOutput.BaseStream,timeout.Token),request.Id);
        }
    }
}
