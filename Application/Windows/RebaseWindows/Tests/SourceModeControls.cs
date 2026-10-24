using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rebase.Windows;

// These tests use authored sessions/audio and do not assert native playback.
static class SourceModeControls
{
    private const string Anchor = "00000000-0000-4000-8000-000000000101";
    private const string Covered = "00000000-0000-4000-8000-000000000102";
    private static readonly string SourceHash = new('a', 64), MediaHash = new('b', 64);
    private static ProjectView Project() => JsonSerializer.Deserialize<ProjectView>($$$"""
        {"id":"project","name":"Modes control","sampleRate":44100,"tempo":120,"tempoMap":{},"signatureMap":[],
         "tracks":[{"id":"track","name":"Retained track","clips":[],"unresolvedAudioEvents":[
          {"id":"{{{Anchor}}}","name":"Anchor","sourceSHA256":"{{{SourceHash}}}","event":{"identityOffset":100},"files":[{"object":{"identityOffset":1000}}]},
          {"id":"{{{Covered}}}","name":"Covered","sourceSHA256":"{{{SourceHash}}}","event":{"identityOffset":101},"files":[{"object":{"identityOffset":1001}}]}]}],
         "cprMediaAttachments":[{"association":"user-selected","sourceSHA256":"{{{SourceHash}}}","sourceFileIdentity":1000,"mediaSHA256":"{{{MediaHash}}}"},
           {"association":"user-selected","sourceSHA256":"{{{SourceHash}}}","sourceFileIdentity":1001,"mediaSHA256":"{{{new string('c', 64)}}}"}]}
        """, ProtocolJson.Options)!;
    private static uint Rate(string mode) => mode switch {
        SourceAuditionMode.Original or "nativeTimelineSourceRate" => 48000,
        "nativeTimelineSavedProjectClock" or SourceAuditionMode.CompleteTrack => 32000, _ => 44100 };
    private static SourceInspectionSnapshot Inspection(ProjectView project, ulong revision = 1) => new() {
        Revision = revision, EventID = Anchor, SourceSHA256 = SourceHash,
        AvailabilityScope = "preparation-only", MaximumFrames = 32_000_000,
        Modes = SourceAuditionMode.All.Select(mode => new SourceModeAvailability { Mode = mode.Id,
            Available = true, SampleRate = Rate(mode.Id), SourceSampleRate = 48000, Frames = Rate(mode.Id) / 10,
            MediaSHA256 = MediaHash, ContributorCount = mode.Id == SourceAuditionMode.CompleteTrack ? 2 : 1,
            FragmentCount = 1 }).ToArray() };

    public static async Task<int> Run()
    {
        int checks = 0;
        void Check(bool value) { checks++; if (!value) throw new Exception("Source mode control " + checks + " failed."); }
        void Reject(Action action) { checks++; try { action(); } catch (Exception error) when (error is InvalidDataException or JsonException or InvalidOperationException or IOException) { return; } throw new Exception("Invalid source mode proof accepted at " + checks); }
        var project = Project(); var selected = SourceEventView.Read(project).Single(s => s.Id == Anchor);
        var validInspection = Inspection(project); validInspection.Validate(1, selected); Check(true);
        foreach (var change in new Action<SourceInspectionSnapshot>[] {
            p => p.Revision++, p => p.EventID = Covered, p => p.SourceSHA256 = new('d',64),
            p => p.AvailabilityScope = "playback-verified", p => p.MaximumFrames++,
            p => p.Modes = p.Modes[..^1], p => p.Modes[1].Mode = p.Modes[0].Mode,
            p => p.Modes[0].Mode = "unknown", p => p.Modes[0].Frames = 0,
            p => p.Modes[0].SampleRate = double.NaN, p => p.Modes[0].SourceSampleRate = 44100.5,
            p => p.Modes[0].MediaSHA256 = new('d',64), p => p.Modes[0].Reason = "contradictory" })
        { var bad = Inspection(project); change(bad); Reject(() => bad.Validate(1, selected)); }
        var unavailable = Inspection(project); unavailable.Modes[0] = new() { Mode = SourceAuditionMode.Original, Available = false, Reason = "Unsupported authored placement." };
        unavailable.Validate(1, selected); Check(true); unavailable.Modes[0].Reason = ""; Reject(() => unavailable.Validate(1, selected));

        var directory = Path.Combine(Path.GetTempPath(), "rebase-source-mode-controls-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(directory);
        try
        {
            RenderSnapshot Render(string mode, double start = 0, bool rewind = false) => SourceControlData.Render(project, selected,
                new() { Command = "renderSourceEvent", Path = Path.Combine(directory,"output.wav"), Mode = mode, StartSeconds = start, RewindAtEnd = rewind },
                1, Rate(mode), Rate(mode) / 10, sourceRate: 48000);
            void Validate(RenderSnapshot r, string mode) => SourceAuditionManifest.Validate(r, r.Path, 1, selected, project, mode);
            foreach (var mode in SourceAuditionMode.All)
            {
                var r = Render(mode.Id); Validate(r, mode.Id);
                var loaded = SnapshotReader.Read(r, r.Path, 1, selected, project, mode.Id);
                Check(loaded.SampleRate == Rate(mode.Id) && loaded.Frames == Rate(mode.Id) / 10);
                if (mode.UsesTimeline && mode.Id != SourceAuditionMode.CompleteTrack)
                {
                    var proof = JsonNode.Parse(File.ReadAllBytes(r.ManifestPath!))!.AsObject();
                    proof["timelineRange"]!["contract"] = mode.Id == "nativeTimelineSourceRate"
                        ? "cpr-15.0.30.287-direct-project-clock-segment-v1" : "cpr-15.0.30.287-direct-source-segment-v1";
                    SourceControlData.WriteProof(r, proof); Reject(() => Validate(r, mode.Id));
                }
            }
            var eof = Render(SourceAuditionMode.Original, 1);
            Check(eof.StartFrame == eof.TotalFrames && eof.Frames == 0 && eof.WavBytes == 58);
            Check(SnapshotReader.Read(eof, eof.Path, 1, selected, project).Samples.Length == 0);
            Reject(() => SnapshotReader.Decode(File.ReadAllBytes(eof.Path), 48000, 0));
            foreach (var change in new Action<RenderSnapshot>[] {
                r => r.Mode = "nativeMode1ProjectRate", r => r.StartFrame = r.TotalFrames + 1,
                r => r.TotalFrames = 0, r => r.TotalFrames = 32_000_001, r => r.Frames--,
                r => r.ManifestBytes = SourceAuditionManifest.MaximumBytes + 1,
                r => r.ManifestSHA256 = new('0',64), r => r.ManifestPath += ".other" })
            { var r = Render(SourceAuditionMode.Original); change(r); Reject(() => Validate(r, SourceAuditionMode.Original)); }
            foreach (var field in new[] { "schema", "revision", "eventID", "mode", "sourceSHA256", "mediaSHA256", "sampleRate", "startFrame", "totalFrames", "frames", "channels", "maximumFrames", "wavFileName", "wavBytes", "wavSHA256", "projectSampleRate", "projectManifestSHA256", "currentProjectSHA256", "importReportSHA256", "sourceSampleRate", "clockRole", "sourceKind" })
            {
                var r = Render(SourceAuditionMode.Original); var proof = JsonNode.Parse(File.ReadAllBytes(r.ManifestPath!))!.AsObject();
                proof.Remove(field); SourceControlData.WriteProof(r, proof); Reject(() => Validate(r, SourceAuditionMode.Original));
            }
            foreach (var change in new Action<JsonObject>[] {
                p => p["clockRole"] = "source-rate",
                p => p["sourceTrack"]!["events"]!.AsArray().RemoveAt(0),
                p => p["sourceTrack"]!["events"]![1]!["sourceOrdinal"] = 0,
                p => p["sourceTrack"]!["events"]![1]!["eventID"] = Anchor,
                p => p["sourceTrack"]!["events"]![0]!["mediaSHA256"] = new string('f',64),
                p => p["sourceTrack"]!["events"]![0]!["eventIdentity"] = 1001,
                p => p["sourceTrack"]!["events"]![0]!["priority"] = 2147483648L,
                p => p["sourceTrack"]!["events"]![0]!["range"]!["contract"] = "cpr-15.0.30.287-direct-source-segment-v1",
                p => p["sourceTrack"]!["fragments"]![0]!["eventID"] = Anchor,
                p => p["sourceTrack"]!["fragments"]![0]!["range"]!["contract"] = "cpr-15.0.30.287-direct-project-clock-segment-v1",
                p => p["sourceTrack"]!["fragments"]![0]!["range"]!["contract"] = "cpr-15.0.30.287-direct-invented-v1",
                p => p["savedProjectAudioSetup"]!["factorBits"] = 0UL })
            {
                var r = Render(SourceAuditionMode.CompleteTrack); var proof = JsonNode.Parse(File.ReadAllBytes(r.ManifestPath!))!.AsObject();
                change(proof); SourceControlData.WriteProof(r,proof); Reject(() => Validate(r,SourceAuditionMode.CompleteTrack));
            }
            var duplicate = Render(SourceAuditionMode.Original); var text = File.ReadAllText(duplicate.ManifestPath!);
            var duplicateBytes = Encoding.UTF8.GetBytes(text.Insert(1,"\"MODE\":\"sourceRate\","));
            File.WriteAllBytes(duplicate.ManifestPath!,duplicateBytes); duplicate.ManifestBytes=(ulong)duplicateBytes.Length; duplicate.ManifestSHA256=SourceControlData.Hash(duplicateBytes);
            Reject(() => Validate(duplicate,SourceAuditionMode.Original));

            var session = new ControlSession(project); var audio = new ControlAudio();
            await using var model = new StudioViewModel(session,audio);
            await model.Open("authored-modes",false,false);
            var original = JsonSerializer.Serialize(model.State,ProtocolJson.Options);
            await model.InspectSource(); Check(model.SourceInspection?.Modes.Length == 8 && session.Inspections == 1);
            Check(JsonSerializer.Serialize(model.State,ProtocolJson.Options) == original && audio.Copies == 0);
            foreach (var mode in SourceAuditionMode.All)
            {
                await model.AuditionSource(mode.Id);
                Check(model.IsPlaying && model.SourcePlaybackMode == mode.Id && session.Last!.Mode == mode.Id && session.Last.StartSeconds == 0 && audio.Rate == Rate(mode.Id));
                await model.Seek(0.025);
                var start = (ulong)Math.Round(0.025 * Rate(mode.Id),MidpointRounding.AwayFromZero);
                Check(model.Position == (double)start / Rate(mode.Id) && audio.LastSeek == 0 && audio.Frames == Rate(mode.Id)/10-start && session.Last!.RewindAtEnd == false);
                audio.Frozen = 3; await model.Pause();
                Check(model.Position == (double)(start+3)/Rate(mode.Id) && !model.IsPlaying);
                await model.Play(); Check(model.IsPlaying && session.Last!.StartSeconds == (double)(start+3)/Rate(mode.Id) && audio.LastSeek == 0);
                var copies=audio.Copies; var plays=audio.Plays; await model.Seek(10);
                Check(model.Position == 0.1 && !model.IsPlaying && audio.Copies == copies && audio.Plays == plays && session.Last!.RewindAtEnd == false);
                await model.Play(); Check(model.IsPlaying && model.Position == 0 && session.Last!.RewindAtEnd == true && audio.Copies == copies+1);
                // Stop discards a prepared suffix. A later timer poll must not
                // restore its old absolute base and make Play resume mid-source.
                await model.Seek(0.025); copies = audio.Copies; var stoppedRenders = session.Renders;
                await model.Stop(); await model.Poll();
                Check(model.Position == 0 && model.IsSourceContext && !model.IsPlaying && model.PlaybackRateInfo is null && session.Renders == stoppedRenders);
                await model.Play();
                Check(model.IsPlaying && model.Position == 0 && session.Last!.StartSeconds == 0 && audio.Copies == copies+1 && audio.LastSeek == 0);
            }
            Check(JsonSerializer.Serialize(model.State,ProtocolJson.Options) == original);
            var renders=session.Renders; await model.AuditionSource("unknown"); Check(session.Renders==renders);
            var oldCopies=audio.Copies; session.WrongMode=true; await model.AuditionSource("nativeMode1ProjectRate");
            Check(!model.IsPlaying && audio.Copies==oldCopies && model.PlaybackRateInfo is null); session.WrongMode=false;
            session.Stale=true; await model.AuditionSource(); Check(!model.IsPlaying && audio.Copies==oldCopies); session.Stale=false;
            session.Fail=true; await model.AuditionSource(); Check(!model.IsPlaying && audio.Copies==oldCopies && model.Status=="Source proof changed."); session.Fail=false;
            await model.RenderSourceTo(Path.Combine(directory,"export.wav"),SourceAuditionMode.CompleteTrack);
            Check(model.LastSourceExport?.Mode==SourceAuditionMode.CompleteTrack && audio.Copies==oldCopies);
        }
        finally { Directory.Delete(directory,true); }
        return checks;
    }
    private sealed class ControlSession(ProjectView project) : ISessionClient
    {
        public int Renders, Inspections; public bool WrongMode, Stale, Fail; public SessionRequest? Last;
        public object[] ModuleReceipt()=>[];
        public ValueTask DisposeAsync()=>ValueTask.CompletedTask;
        public Task<SessionResponse> Send(SessionRequest request)
        {
            var response=new SessionResponse { Protocol=1,Id=request.Id,Ok=true, State=new() { Revision=1,Project=project,Selection=new() { TrackID="track",ClipID=Anchor } } };
            if(request.Command=="inspectSourceEvent") { Inspections++; response.SourceInspection=Inspection(project); }
            if(request.Command=="renderSourceEvent")
            {
                Last=request; Renders++;
                if(Fail) { response.Ok=false; response.Error=new() { Message="Source proof changed." }; }
                else { var mode=request.Mode??SourceAuditionMode.Original; response.Render=SourceControlData.Render(project,SourceEventView.Read(project).Single(s=>s.Id==Anchor),request,Stale?2UL:1UL,Rate(mode),Rate(mode)/10,sourceRate:48000); if(WrongMode)response.Render.Mode=SourceAuditionMode.Original; }
            }
            return Task.FromResult(response);
        }
    }
    private sealed class ControlAudio : IAudioOutput
    {
        public uint Rate; public ulong Frames, LastSeek, Frozen; private ulong position; private uint phase;
        public int Copies,Plays;
        public Task<DeviceFormat> Format()=>Task.FromResult(new DeviceFormat { SampleRate=48000,Channels=2,Float32=1 });
        public Task SetSource(LoadedSnapshot source) { Copies++; Rate=source.SampleRate;Frames=source.Frames;position=0;phase=1;return Task.CompletedTask; }
        public Task<AudioRateInfo> RateInfo()=>Task.FromResult(new AudioRateInfo { AbiVersion=1,SourceRate=Rate,EndpointRate=48000,SourceFrames=Frames,EndpointFrames=(Frames*48000+Rate-1)/Rate,Converted=Rate==48000?0u:1u,SoxrRecipe=Rate==48000?0u:6u });
        public Task<AudioStatus> Status()=>Task.FromResult(new AudioStatus { AbiVersion=1,SampleRate=Rate,TotalFrames=Frames,PositionFrames=position,SubmittedFrames=Frames,Phase=phase });
        public Task Play() { Plays++;phase=2;return Task.CompletedTask; }
        public Task Pause() { position=Frozen;phase=3;return Task.CompletedTask; }
        public Task Stop() { position=0;phase=1;return Task.CompletedTask; }
        public Task Seek(ulong frame) { LastSeek=frame;position=frame;return Task.CompletedTask; }
        public ValueTask DisposeAsync()=>ValueTask.CompletedTask;
    }
}

// Authored protocol receipts for host controls, never helper or device evidence.
static class SourceControlData
{
    public static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes));
    public static byte[] Wave(uint rate, ulong frames, ulong first = 0)
    {
        var bytes = new byte[checked(58 + (int)frames * 8)];
        Encoding.ASCII.GetBytes("RIFF").CopyTo(bytes, 0); BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(4), (uint)bytes.Length - 8);
        Encoding.ASCII.GetBytes("WAVEfmt ").CopyTo(bytes, 8); BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(16), 18);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(20), 3); BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(22), 2);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(24), rate); BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(28), rate * 8);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(32), 8); BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(34), 32);
        Encoding.ASCII.GetBytes("fact").CopyTo(bytes, 38); BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(42), 4);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(46), checked((uint)frames));
        Encoding.ASCII.GetBytes("data").CopyTo(bytes, 50); BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(54), checked((uint)frames * 8));
        for (ulong i = 0; i < frames; i++)
        {
            float sample = (first + i) % 100 / 100f;
            BinaryPrimitives.WriteSingleLittleEndian(bytes.AsSpan(checked(58 + (int)i * 8)), sample);
            BinaryPrimitives.WriteSingleLittleEndian(bytes.AsSpan(checked(62 + (int)i * 8)), -sample);
        }
        return bytes;
    }
    public static RenderSnapshot Render(ProjectView project, SourceEventView selected, SessionRequest request,
        ulong revision, uint rate, ulong total, string? mediaHash = null, double sourceRate = 0)
    {
        var start = (ulong)Math.Clamp(Math.Round((request.StartSeconds ?? 0) * rate, MidpointRounding.AwayFromZero), 0, total);
        if (start == total && request.RewindAtEnd == true) start = 0;
        var bytes = Wave(rate, total - start, start); File.WriteAllBytes(request.Path!, bytes);
        var mode = request.Mode ?? SourceAuditionMode.Original;
        var render = new RenderSnapshot { Kind = "sourceEvent", Path = request.Path!, Revision = revision,
            EventID = selected.Id, SourceSHA256 = selected.SourceSHA256, MediaSHA256 = mediaHash ?? selected.MediaSHA256,
            Mode = mode, StartFrame = start, TotalFrames = total, SampleRate = rate, Frames = total - start,
            Channels = 2, WavBytes = (ulong)bytes.Length, Sha256 = Hash(bytes) };
        var proof = new JsonObject
        {
            ["schema"] = "rebase.source-audition-manifest.v1", ["revision"] = revision,
            ["eventID"] = selected.Id, ["mode"] = mode, ["sourceSHA256"] = selected.SourceSHA256,
            ["mediaSHA256"] = render.MediaSHA256, ["sampleRate"] = rate, ["frames"] = render.Frames,
            ["startFrame"] = start, ["totalFrames"] = total, ["channels"] = 2, ["maximumFrames"] = 32_000_000,
            ["wavFileName"] = Path.GetFileName(request.Path), ["wavBytes"] = render.WavBytes,
            ["wavSHA256"] = render.Sha256, ["projectSampleRate"] = project.SampleRate,
            ["projectManifestSHA256"] = new string('c', 64), ["currentProjectSHA256"] = new string('d', 64),
            ["importReportSHA256"] = new string('e', 64), ["sourceSampleRate"] = sourceRate == 0 ? rate : sourceRate,
            ["sourceKind"] = mode == SourceAuditionMode.CompleteTrack ? "track" : "event",
            ["clockRole"] = mode switch {
                SourceAuditionMode.Original => "source-rate", "nativeTimelineSourceRate" => "source-clock-unconverted",
                "nativeTimelineProjectClock" => "current-project-clock-unconverted",
                "nativeTimelineSavedProjectClock" or SourceAuditionMode.CompleteTrack => "saved-project-clock-unconverted",
                _ => "current-project-rate-converted" }
        };
        if (project.TempoMap.ValueKind == JsonValueKind.Object && project.TempoMap.TryGetProperty("nativeClock", out var clock))
            proof["currentNativeClock"] = JsonNode.Parse(clock.GetRawText());
        if (SourceAuditionMode.Find(mode).UsesTimeline)
        {
            proof["preservedNativeClock"] = new JsonObject { ["sourceSHA256"] = selected.SourceSHA256 };
            proof["timelineRange"] = Range(mode, (double)total / rate);
        }
        if (mode is "nativeTimelineSavedProjectClock" or SourceAuditionMode.CompleteTrack)
            proof["savedProjectAudioSetup"] = new JsonObject {
                ["contract"] = "cpr-15.0.30.287-parrangement-audio-setup-v1", ["sourceSHA256"] = selected.SourceSHA256,
                ["factorBits"] = 0x3ff0000000000000UL, ["baseRateBits"] = BitConverter.SingleToUInt32Bits(rate) };
        if (mode == SourceAuditionMode.CompleteTrack)
        {
            var track = project.Tracks.Single(t => t.UnresolvedAudioEvents.Any(e => e.GetProperty("id").GetString() == selected.Id));
            var sources = SourceEventView.Read(project); var events = new JsonArray();
            for (var i = 0; i < track.UnresolvedAudioEvents.Length; i++)
            {
                var retained = track.UnresolvedAudioEvents[i]; var id = retained.GetProperty("id").GetString()!;
                events.Add(new JsonObject { ["eventID"] = id, ["eventIdentity"] = retained.GetProperty("event").GetProperty("identityOffset").GetInt32(),
                    ["sourceOrdinal"] = i, ["priority"] = i == 0 ? int.MinValue : int.MaxValue,
                    ["sourceSampleRate"] = sourceRate == 0 ? rate : sourceRate, ["mediaSHA256"] = sources.Single(s => s.Id == id).MediaSHA256,
                    ["canonicalStart"] = 0, ["canonicalEnd"] = (double)total / rate, ["range"] = Range(mode, (double)total / rate) });
            }
            var winner = events[^1]!.AsObject();
            proof["sourceTrack"] = new JsonObject { ["contract"] = "cpr-15.0.30.287-priority-track-fresh-root-mode0-v1", ["freshRootMode"] = 0,
                ["trackIdentity"] = 200, ["events"] = events, ["fragments"] = new JsonArray(new JsonObject {
                    ["eventID"] = winner["eventID"]!.DeepClone(), ["eventIdentity"] = winner["eventIdentity"]!.DeepClone(),
                    ["sourceOrdinal"] = winner["sourceOrdinal"]!.DeepClone(), ["range"] = Range(mode, (double)total / rate) }),
                ["snappedEmptyFragmentCount"] = 0 };
        }
        WriteProof(render, proof); return render;
    }
    public static JsonObject Range(string mode, double duration) => new() {
        ["contract"] = mode switch { "nativeTimelineSourceRate" => "cpr-15.0.30.287-direct-source-segment-v1",
            "nativeTimelineProjectClock" => "cpr-15.0.30.287-direct-project-clock-segment-v1", _ => "cpr-15.0.30.287-direct-saved-project-clock-segment-v1" },
        ["position"] = 0, ["duration"] = duration, ["offset"] = 0 };
    public static void WriteProof(RenderSnapshot render, JsonObject proof)
    {
        var bytes = Encoding.UTF8.GetBytes(proof.ToJsonString()); render.ManifestPath = render.Path + SourceAuditionManifest.Suffix;
        File.WriteAllBytes(render.ManifestPath, bytes); render.ManifestBytes = (ulong)bytes.Length; render.ManifestSHA256 = Hash(bytes);
    }
    public static void Delete(string path) { File.Delete(path); File.Delete(path + SourceAuditionManifest.Suffix); }
}
