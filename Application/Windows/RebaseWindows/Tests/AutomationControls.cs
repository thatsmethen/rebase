using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rebase.Windows;

static class AutomationControls
{
    private const string TrackID = "00000000-0000-4000-8000-000000000001";
    private const string LaneID = "00000000-0000-4000-8000-000000000002";
    private const string PointID = "00000000-0000-4000-8000-000000000003";
    public static async Task<int> Run()
    {
        int checks = 0;
        void Check(bool good) { checks++; if (!good) throw new Exception("Automation host control " + checks + " failed."); }
        void Reject(Action action) { checks++; try { action(); } catch (InvalidDataException) { return; } throw new Exception("Malformed automation projection accepted."); }
        var project = Project(); var track = project.Tracks.Single();
        var raw = JsonSerializer.Serialize(track, ProtocolJson.Options);
        var lane = AutomationLaneView.ReadVolume(track)!;
        Check(lane.Id == LaneID && lane.IsReadEnabled && lane.Points.Single().Id == PointID && lane.Points[0].Value == -7);
        Check(AutomationLaneView.Read(track, "pan") is { IsReadEnabled: false, Points.Count: 1 } pan && pan.Points[0].Value == 0.25);
        Check(JsonSerializer.Serialize(track, ProtocolJson.Options) == raw && track.AdditionalFields!["unknownTrack"].GetString() == "retained");
        Check(AutomationLaneView.ReadVolume(new()) is null);
        foreach (var mutate in new Action<JsonObject>[] {
            p => p["id"] = "bad", p => p.Remove("points"), p => p["isReadEnabled"] = "yes",
            p => p["points"]![0]!["time"] = -1, p => p["points"]![0]!["time"] = 86401,
            p => p["points"]![0]!["value"] = -97, p => p["points"]![0]!["value"] = 25,
            p => p["points"]![0]!["interpolation"] = "bezier", p => p["points"]![0]!.AsObject().Remove("id"),
            p => p["points"]!.AsArray().Add(p["points"]![0]!.DeepClone()) })
        {
            var invalid = JsonNode.Parse(raw)!.AsObject(); mutate(invalid["automation"]![0]!.AsObject());
            Reject(() => AutomationLaneView.ReadVolume(invalid.Deserialize<TrackView>(ProtocolJson.Options)!));
        }
        var duplicate = JsonNode.Parse(raw)!; duplicate["automation"]!.AsArray().Add(duplicate["automation"]![0]!.DeepClone());
        Reject(() => AutomationLaneView.ReadVolume(duplicate.Deserialize<TrackView>(ProtocolJson.Options)!));
        var invalidPan = JsonNode.Parse(raw)!; invalidPan["automation"]![1]!["points"]![0]!["value"] = 1.01;
        Reject(() => AutomationLaneView.Read(invalidPan.Deserialize<TrackView>(ProtocolJson.Options)!, "pan"));
        var large = JsonNode.Parse(raw)!; var largePoints = new JsonArray();
        for (int i = 0; i < 4097; i++) largePoints.Add(JsonSerializer.SerializeToNode(new { id = Guid.NewGuid().ToString(), time = (double)i, value = -6, interpolation = "linear" }));
        large["automation"]![0]!["points"] = largePoints;
        Check(AutomationLaneView.ReadVolume(large.Deserialize<TrackView>(ProtocolJson.Options)!)!.Points.Count == 4097);
        var client = new ControlSession(project); var audio = new ControlAudio();
        await using var model = new StudioViewModel(client, audio);
        await model.Open("authored-control", false, false);
        string State() => JsonSerializer.Serialize(model.State, ProtocolJson.Options);
        var initial = State(); var revision = model.State.Revision;
        Check(!await model.UpsertAutomationPoint(TrackID, PointID, 2, -4, "linear", revision - 1) && client.Edits.Count == 0 && State() == initial);
        Check(!await model.RemoveAutomationPoint("missing", PointID, revision) && client.Edits.Count == 0 && State() == initial);
        client.Fail = true;
        Check(!await model.UpsertAutomationPoint(TrackID, PointID, 2, -4, "step", revision) && client.Edits.Count == 1 && State() == initial && model.Status == "Authored rejection.");
        client.Fail = false;
        Check(await model.UpsertAutomationPoint(TrackID, PointID, 2, -4, "step", revision));
        var request = client.Edits[^1];
        Check(request.Command == "upsertAutomationPoint" && request.Parameter == "gainDB" && request.PointID == PointID && request.Time == 2 && request.Value == -4 && request.Interpolation == "step" && request.ExpectedRevision == revision);
        Check(model.State.Revision == revision + 1 && model.State.Dirty && model.State.CanUndo);
        Check(await model.SetAutomationRead(TrackID, false, model.State.Revision, "pan") && client.Edits[^1].Parameter == "pan" && client.Edits[^1].Enabled == false);
        Check(await model.RemoveAutomationPoint(TrackID, PointID, model.State.Revision) && client.Edits[^1].Command == "removeAutomationPoint");
        Check(await model.AutomationHistory("undo", TrackID, model.State.Revision) && client.Edits[^1].Command == "undo");
        Check(await model.AutomationHistory("redo", TrackID, model.State.Revision) && client.Edits[^1].Command == "redo");
        var serialized = JsonSerializer.Serialize(client.Edits[1], ProtocolJson.Options);
        using (var json = JsonDocument.Parse(serialized))
            Check(json.RootElement.GetProperty("pointID").GetString() == PointID && json.RootElement.GetProperty("parameter").GetString() == "gainDB" && json.RootElement.GetProperty("time").GetDouble() == 2);
        // A second caller can queue while the first is in flight. The draft's
        // original revision is checked after acquiring the same action gate.
        client.Delay = new(TaskCreationOptions.RunContinuationsAsynchronously);
        revision = model.State.Revision; var editCount = client.Edits.Count;
        var first = model.UpsertAutomationPoint(TrackID, null, 3, -6, "linear", revision);
        var staleQueued = model.SetAutomationRead(TrackID, true, revision);
        client.Delay.SetResult(); Check(await first); Check(!await staleQueued && client.Edits.Count == editCount + 1);
        client.Delay = null;
        await model.PlayProject(); Check(model.IsPlaying && audio.SourceCopies == 1 && client.Renders == 1);
        var stops = audio.Stops;
        Check(await model.SetAutomationRead(TrackID, false, model.State.Revision));
        Check(!model.IsPlaying && audio.Stops == stops + 1);
        await model.PlayProject(); Check(model.IsPlaying && audio.SourceCopies == 2 && client.Renders == 2);
        client.Fail = true; stops = audio.Stops;
        Check(!await model.RemoveAutomationPoint(TrackID, PointID, model.State.Revision) && model.IsPlaying && audio.Stops == stops);
        Check(JsonSerializer.Serialize(model.SelectedTrack, ProtocolJson.Options) == raw); // Fake replies deliberately preserve document payload.
        return checks;
    }
    private static ProjectView Project() => JsonSerializer.Deserialize<ProjectView>($$"""
        {"id":"project","name":"Authored automation","sampleRate":48000,"tempo":120,"tempoMap":[],"signatureMap":[],"tracks":[{"id":"{{TrackID}}","name":"Control","gainDB":-2,"pan":0,"clips":[],"unknownTrack":"retained","automation":[
          {"id":"{{LaneID}}","parameter":"gainDB","isReadEnabled":true,"unknownLane":7,"points":[{"id":"{{PointID}}","time":1,"value":-7,"interpolation":"linear"}]},
          {"id":"00000000-0000-4000-8000-000000000004","parameter":"pan","isReadEnabled":false,"points":[{"id":"00000000-0000-4000-8000-000000000005","time":1,"value":0.25,"interpolation":"step"}]}]}]}
        """, ProtocolJson.Options)!;
    private sealed class ControlSession(ProjectView project) : ISessionClient
    {
        private ulong revision = 1;
        public readonly List<SessionRequest> Edits = [];
        public bool Fail;
        public int Renders;
        public TaskCompletionSource? Delay;
        public object[] ModuleReceipt() => [];
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
        public async Task<SessionResponse> Send(SessionRequest request)
        {
            var edit = request.Command is "upsertAutomationPoint" or "removeAutomationPoint" or "setAutomationRead" or "undo" or "redo";
            if (edit)
            {
                Edits.Add(request); if (Delay is { } delay) await delay.Task;
                if (!Fail) revision++;
            }
            var reply = new SessionResponse { Protocol = 1, Id = request.Id, Ok = !(edit && Fail),
                State = new() { Revision = revision, Dirty = revision > 1, CanUndo = revision > 1, Project = project, Selection = new() { TrackID = TrackID } },
                Error = edit && Fail ? new() { Message = "Authored rejection." } : null };
            if (request.Command == "render")
            {
                Renders++; var wave = new byte[60];
                Encoding.ASCII.GetBytes("RIFF").CopyTo(wave, 0); BinaryPrimitives.WriteUInt32LittleEndian(wave.AsSpan(4), 52);
                Encoding.ASCII.GetBytes("WAVEfmt ").CopyTo(wave, 8); BinaryPrimitives.WriteUInt32LittleEndian(wave.AsSpan(16), 16);
                BinaryPrimitives.WriteUInt16LittleEndian(wave.AsSpan(20), 3); BinaryPrimitives.WriteUInt16LittleEndian(wave.AsSpan(22), 2);
                BinaryPrimitives.WriteUInt32LittleEndian(wave.AsSpan(24), 48000); BinaryPrimitives.WriteUInt32LittleEndian(wave.AsSpan(28), 384000);
                BinaryPrimitives.WriteUInt16LittleEndian(wave.AsSpan(32), 8); BinaryPrimitives.WriteUInt16LittleEndian(wave.AsSpan(34), 32);
                Encoding.ASCII.GetBytes("data").CopyTo(wave, 36); BinaryPrimitives.WriteUInt32LittleEndian(wave.AsSpan(40), 16);
                File.WriteAllBytes(request.Path!, wave);
                reply.Render = new() { Kind = "project", Path = request.Path!, Revision = revision, SampleRate = 48000, Frames = 2, Channels = 2, WavBytes = 60, Sha256 = Convert.ToHexString(SHA256.HashData(wave)) };
            }
            return reply;
        }
    }
    private sealed class ControlAudio : IAudioOutput
    {
        public int SourceCopies, Stops;
        public Task<DeviceFormat> Format() => Task.FromResult(new DeviceFormat { SampleRate = 48000, Channels = 2, Float32 = 1 });
        public Task<AudioStatus> Status() => Task.FromResult(new AudioStatus { AbiVersion = 1, SampleRate = 48000 });
        public Task SetSource(LoadedSnapshot source) { SourceCopies++; return Task.CompletedTask; }
        public Task Play() => Task.CompletedTask;
        public Task Pause() => Task.CompletedTask;
        public Task Stop() { Stops++; return Task.CompletedTask; }
        public Task Seek(ulong frame) => Task.CompletedTask;
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
