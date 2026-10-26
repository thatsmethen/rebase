using System.Text.Json;
using Rebase.Windows;

// Host decisions only. Actual decoding/publication is exercised separately by
// the shared helper and the native-window journey.
static class DocumentsControls
{
    public static async Task<int> Run()
    {
        var checks = 0;
        void Check(bool value) { checks++; if (!value) throw new Exception("Document host control " + checks + " failed."); }
        string Identity(StudioViewModel value) => JsonSerializer.Serialize(value.State, ProtocolJson.Options);
        var client = new Client(); var audio = new Device();
        await using (var model = new StudioViewModel(client, audio))
        {
            Check(!await model.ImportAudio(["first.wav"]) && client.Mutations.Count == 0);
            Check(await model.NewProject() && model.Project?.Name == "Untitled" && model.Project.Tracks.Length == 0);
            Check(model.State.NeedsSaveAs && model.State.Path is null && !model.State.Dirty && !model.State.CanUndo && !model.State.CanRedo);
            Check(model.State.Selection.TrackID is null && model.State.Selection.ClipID is null && model.Position == 0);
            var create = client.Mutations.Single();
            Check(create.Command == "newProject" && create.ExpectedRevision == 0 && create.DiscardChanges == false &&
                create.Path is not null && Path.IsPathFullyQualified(create.Path) && create.Path.EndsWith(".rebaseproj", StringComparison.Ordinal) && !Directory.Exists(create.Path));
            var revision = model.State.Revision;
            model.Snap = "eighth";
            Check(await model.ImportAudio(["first.wav", "second.wav"], 1.125));
            var imported = client.Mutations.Last();
            Check(imported.Command == "importAudio" && imported.Paths!.SequenceEqual(new[] { "first.wav", "second.wav" }) &&
                imported.Value == 1.125 && imported.Snap == "eighth" && imported.ExpectedRevision == revision);
            Check(model.State.Revision == revision + 1 && model.Project!.Tracks.Length == 2 && model.State.Dirty && model.State.CanUndo);
            Check(model.SelectedTrack?.Name == "second" && model.SelectedClip?.Name == "second");
            var projectBytes = JsonSerializer.Serialize(model.Project, ProtocolJson.Options);
            await model.Command("undo");
            Check(model.Project!.Tracks.Length == 0 && !model.State.CanUndo && model.State.CanRedo);
            await model.Command("redo");
            Check(JsonSerializer.Serialize(model.Project, ProtocolJson.Options) == projectBytes && model.State.CanUndo && !model.State.CanRedo);
            // A queued import belongs to the document revision observed when
            // the file/position intent was supplied, not a later queued state.
            foreach (var replace in new[] { false, true })
            {
                var undoEntered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                var undoRelease = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                client.BeforeUndo = async () => { undoEntered.SetResult(); await undoRelease.Task; };
                var pendingUndo = model.Command("undo");
                await undoEntered.Task.WaitAsync(TimeSpan.FromSeconds(5));
                var requestsBeforeDrift = client.Mutations.Count;
                var staleIntent = replace ? model.NewProject(discardChanges: true) : model.ImportAudio(["queued.wav"], 1.125);
                undoRelease.SetResult(); await pendingUndo;
                Check(!await staleIntent && client.Mutations.Count == requestsBeforeDrift && model.Project!.Tracks.Length == 0);
                Check(model.Status.StartsWith("The project changed while ", StringComparison.Ordinal));
                client.BeforeUndo = null; await model.Command("redo");
                Check(JsonSerializer.Serialize(model.Project, ProtocolJson.Options) == projectBytes);
            }
            var before = Identity(model); var calls = client.Mutations.Count;
            Check(!await model.NewProject() && Identity(model) == before && client.Mutations.Count == calls);
            client.FailImport = true;
            Check(!await model.ImportAudio(["valid.wav", "invalid.wav"]) && Identity(model) == before && model.Status == "Authored batch rejection.");
            Check(client.Mutations.Count == calls + 1); // no automatic retry
            client.FailImport = false;
            foreach (var paths in new[] { Array.Empty<string>(), new[] { "" }, Enumerable.Repeat("a.wav", 33).ToArray() })
            { calls = client.Mutations.Count; Check(!await model.ImportAudio(paths) && client.Mutations.Count == calls); }
            foreach (var seconds in new[] { double.NaN, double.PositiveInfinity, -1, 86400.1 })
            { calls = client.Mutations.Count; Check(!await model.ImportAudio(["a.wav"], seconds) && client.Mutations.Count == calls); }
            model.Snap = "unknown"; calls = client.Mutations.Count;
            Check(!await model.ImportAudio(["a.wav"]) && client.Mutations.Count == calls); model.Snap = "off";
            client.FailSave = true;
            Check(!await model.Save() && !model.State.Dirty && model.NeedsSaveDecision);
            calls = client.Mutations.Count;
            Check(!await model.NewProject() && client.Mutations.Count == calls && model.NeedsSaveDecision);
            client.FailSave = false;
            Check(await model.Save("kept.rebaseproj") && !model.NeedsSaveDecision && !model.State.NeedsSaveAs);
            Check(await model.NewProject() && model.Project!.Tracks.Length == 0 && !model.NeedsSaveDecision);
            Check(client.Mutations.Last().Path != create.Path);
            Check(await model.ImportAudio(["third.wav"]));
            Check(await model.NewProject(discardChanges: true) && client.Mutations.Last().DiscardChanges == true && !model.NeedsSaveDecision);
            using var wire = JsonDocument.Parse(JsonSerializer.Serialize(imported, ProtocolJson.Options));
            Check(wire.RootElement.GetProperty("paths").GetArrayLength() == 2 && wire.RootElement.GetProperty("expectedRevision").GetUInt64() == revision);
        }
        // A native Stop failure must prevent either request, preserving the
        // installed snapshot/position so Stop can be retried explicitly.
        foreach (var replace in new[] { false, true })
        {
            client = new Client(); audio = new Device();
            await using var model = new StudioViewModel(client, audio);
            await model.NewProject(); await model.ImportAudio(["first.wav"]); await model.Play(); await model.Seek(0.025);
            var before = Identity(model); var position = model.Position; var calls = client.Mutations.Count;
            audio.FailStop = true;
            var success = replace ? await model.NewProject(true) : await model.ImportAudio(["second.wav"]);
            Check(!success && Identity(model) == before && client.Mutations.Count == calls && model.Position == position);
            Check(model.Status == "Authored native stop failure." && model.IsPlaying);
            audio.FailStop = false; await model.Stop();
            Check(model.Status == "Stopped" && model.Position == 0);
            Check(replace ? await model.NewProject(true) : await model.ImportAudio(["second.wav"]));
        }
        return checks;
    }

    private sealed class Client : ISessionClient
    {
        public List<SessionRequest> Mutations { get; } = [];
        public bool FailImport, FailSave;
        public Func<Task>? BeforeUndo;
        private SessionState state = new();
        private ProjectView? beforeImport, afterImport;
        private static T Copy<T>(T value) => JsonSerializer.Deserialize<T>(JsonSerializer.Serialize(value, ProtocolJson.Options), ProtocolJson.Options)!;
        public object[] ModuleReceipt() => [];
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
        public async Task<SessionResponse> Send(SessionRequest request)
        {
            if (request.Command == "undo" && BeforeUndo is not null) await BeforeUndo();
            if (request.Command is "newProject" or "importAudio") Mutations.Add(request);
            var response = new SessionResponse { Protocol = 1, Ok = true };
            if (request.Command is not ("waveform" or "ruler") && request.ExpectedRevision != state.Revision)
                throw new Exception("Document command omitted its current revision.");
            switch (request.Command)
            {
                case "newProject":
                    state = new() { Revision = state.Revision + 1, NeedsSaveAs = true, Project = new() {
                        Id = Guid.NewGuid().ToString(), Name = "Untitled", SampleRate = 48000, Tempo = 120,
                        TempoMap = JsonSerializer.SerializeToElement(new { }), SignatureMap = JsonSerializer.SerializeToElement(new { }) } };
                    beforeImport = afterImport = null; break;
                case "importAudio":
                    if (FailImport) { response.Ok = false; response.Error = new() { Message = "Authored batch rejection." }; break; }
                    beforeImport = Copy(state.Project!);
                    var tracks = request.Paths!.Select(path => new TrackView { Id = Guid.NewGuid().ToString(), Name = Path.GetFileNameWithoutExtension(path),
                        Clips = [new() { Id = Guid.NewGuid().ToString(), Name = Path.GetFileNameWithoutExtension(path), Duration = 1,
                            Position = request.Value!.Value, MediaPath = "Media/" + Path.GetFileName(path) }] }).ToArray();
                    state.Project!.Tracks = [..state.Project.Tracks, ..tracks];
                    state.Selection = new() { TrackID = tracks[^1].Id, ClipID = tracks[^1].Clips[0].Id };
                    state.Revision++; state.Dirty = true; state.CanUndo = true; state.CanRedo = false; afterImport = Copy(state.Project); break;
                case "undo": state.Project = Copy(beforeImport!); state.Selection = new(); state.CanUndo = false; state.CanRedo = true; state.Revision++; break;
                case "redo": state.Project = Copy(afterImport!); state.CanUndo = true; state.CanRedo = false; state.Revision++; break;
                case "save": case "saveAs":
                    state.Dirty = false;
                    if (FailSave) { response.Ok = false; response.Error = new() { Message = "Authored save failure." }; }
                    else if (request.Command == "saveAs") { state.Path = request.Path; state.NeedsSaveAs = false; state.Revision++; }
                    break;
                case "render":
                    var bytes = SourceControlData.Wave(48000, 4800); File.WriteAllBytes(request.Path!, bytes);
                    response.Render = new() { Kind = "project", Path = request.Path!, Revision = state.Revision,
                        SampleRate = 48000, Frames = 4800, Channels = 2, WavBytes = (ulong)bytes.Length, Sha256 = SourceControlData.Hash(bytes) }; break;
                case "waveform": case "ruler": response.Ok = false; response.Error = new() { Message = "No authored projection." }; break;
            }
            response.State = Copy(state); return response;
        }
    }
    private sealed class Device : IAudioOutput
    {
        private LoadedSnapshot? installed; private ulong position; private uint phase;
        public bool FailStop;
        public Task<DeviceFormat> Format() => Task.FromResult(new DeviceFormat { SampleRate = 48000, Channels = 2, Float32 = 1 });
        public Task SetSource(LoadedSnapshot source) { installed = source; position = 0; phase = 1; return Task.CompletedTask; }
        public Task<AudioRateInfo> RateInfo() => Task.FromResult(new AudioRateInfo { AbiVersion = 1, SourceRate = 48000, EndpointRate = 48000,
            SourceFrames = installed!.Frames, EndpointFrames = installed.Frames });
        public Task<AudioStatus> Status() => Task.FromResult(new AudioStatus { AbiVersion = 1, Phase = phase, SampleRate = 48000,
            PositionFrames = position, TotalFrames = installed!.Frames, SubmittedFrames = installed.Frames });
        public Task Play() { phase = 2; return Task.CompletedTask; }
        public Task Pause() { phase = 3; return Task.CompletedTask; }
        public Task Seek(ulong frame) { position = frame; return Task.CompletedTask; }
        public Task Stop() { if (FailStop) throw new IOException("Authored native stop failure."); position = 0; phase = 1; return Task.CompletedTask; }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
