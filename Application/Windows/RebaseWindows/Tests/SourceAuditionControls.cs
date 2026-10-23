using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Rebase.Windows;

static class SourceAuditionControls
{
    private const string EventID = "00000000-0000-4000-8000-000000000001";
    private static readonly string SourceHash = new('a', 64), MediaHash = new('b', 64);
    public static async Task<int> Run()
    {
        int checks = 0;
        void Check(bool value) { checks++; if (!value) throw new Exception("Source audition control " + checks + " failed."); }
        void Reject(Action action) { checks++; try { action(); } catch (InvalidDataException) { return; } throw new Exception("Source context accepted an invalid receipt."); }
        var project = JsonSerializer.Deserialize<ProjectView>($$$"""
            {"id":"project","name":"Source control","sampleRate":44100,"tempo":120,"unknownProject":{"retained":true},
             "tracks":[{"id":"track","name":"Retained track","unknownTrack":7,"clips":[],
              "unresolvedAudioEvents":[{"id":"{{{EventID}}}","name":"Source event","sourceSHA256":"{{{SourceHash}}}",
                "unknownEvent":[1,2,3],"files":[{"object":{"identityOffset":1024}}]}]}],
             "cprMediaAttachments":[{"association":"user-selected","sourceSHA256":"{{{SourceHash}}}",
                "sourceFileIdentity":1024,"mediaSHA256":"{{{MediaHash}}}","unknownAttachment":"retained"}]}
            """, ProtocolJson.Options)!;
        var selected = SourceEventView.Read(project).Single();
        Check(selected.Id == EventID && selected.MediaSHA256 == MediaHash && selected.DisplayName == "Retained track — Source event");
        Check(project.AdditionalFields!["unknownProject"].GetProperty("retained").GetBoolean() && project.Tracks[0].AdditionalFields!["unknownTrack"].GetInt32() == 7);
        Check(project.Tracks[0].UnresolvedAudioEvents[0].GetProperty("unknownEvent").GetArrayLength() == 3 && project.CprMediaAttachments[0].GetProperty("unknownAttachment").GetString() == "retained");
        RenderSnapshot Receipt() => new() { Kind = "sourceEvent", EventID = EventID, SourceSHA256 = SourceHash, MediaSHA256 = MediaHash };
        SnapshotReader.ValidateContext(Receipt(), selected); Check(true);
        Reject(() => SnapshotReader.ValidateContext(Receipt(), null));
        Reject(() => SnapshotReader.ValidateContext(new() { Kind = "project" }, selected));
        var invalid = Receipt(); invalid.EventID = Guid.NewGuid().ToString(); Reject(() => SnapshotReader.ValidateContext(invalid, selected));
        invalid = Receipt(); invalid.SourceSHA256 = new string('c', 64); Reject(() => SnapshotReader.ValidateContext(invalid, selected));
        invalid = Receipt(); invalid.MediaSHA256 = new string('c', 64); Reject(() => SnapshotReader.ValidateContext(invalid, selected));
        Reject(() => SnapshotReader.ValidateContext(Receipt(), selected with { MediaSHA256 = null }));
        Reject(() => SnapshotReader.ValidateContext(new(), null));
        var duplicate = project.CprMediaAttachments;
        project.CprMediaAttachments = [duplicate[0], duplicate[0]];
        Check(SourceEventView.Read(project).Single().MediaSHA256 is null);
        project.CprMediaAttachments = duplicate;

        var session = new ControlSession(project); var audio = new ControlAudio();
        await using var model = new StudioViewModel(session, audio);
        await model.Open("synthetic-control", false, false);
        var export = Path.Combine(Path.GetTempPath(), "rebase-source-control-" + Guid.NewGuid().ToString("N") + ".wav");
        try
        {
            await model.RenderSourceTo(export);
            Check(model.Status.StartsWith("Exported source WAV:", StringComparison.Ordinal) && audio.FormatCalls == 0 && File.Exists(export));
        }
        finally { File.Delete(export); }
        await model.AuditionSource();
        Check(model.IsSourceContext && model.IsPlaying && session.SourceRenders == 2 && audio.SourceRate == 48000 && project.SampleRate == 44100);
        Check(model.TransportContext.Contains("event-local seconds", StringComparison.Ordinal));
        await model.Pause(); Check(!model.IsPlaying && session.SourceRenders == 2);
        await model.Play(); Check(model.IsPlaying && session.SourceRenders == 3 && audio.SourceCopies == 2);
        await model.Seek(0.005); Check(session.SourceRenders == 4 && audio.LastSeek == 240 && model.Position == 0.005 && model.IsPlaying);
        await model.Pause(); var plays = audio.Plays;
        await model.Seek(0.002); Check(session.SourceRenders == 5 && audio.LastSeek == 96 && audio.Plays == plays && !model.IsPlaying);
        await model.Play(); Check(session.SourceRenders == 6 && audio.LastSeek == 96 && model.IsPlaying);
        var copies = audio.SourceCopies; plays = audio.Plays; var stops = audio.Stops;
        session.WrongMediaReceipt = true;
        await model.Play(); Check(session.SourceRenders == 7 && audio.Stops > stops && audio.Plays == plays && audio.SourceCopies == copies && !model.IsPlaying);
        session.WrongMediaReceipt = false; session.FailSourceRender = true;
        await model.Play(); Check(session.SourceRenders == 8 && audio.Plays == plays && model.Status == "Source changed outside the session.");
        session.FailSourceRender = false; audio.Rate = 44100;
        await model.Play(); Check(session.SourceRenders == 9 && audio.SourceCopies == copies && model.Status.Contains("source event uses 48000 Hz", StringComparison.Ordinal));
        audio.Rate = 48000; await model.Play(); Check(session.SourceRenders == 10 && model.IsPlaying);
        audio.DelayedStatus = new(TaskCreationOptions.RunContinuationsAsynchronously);
        var polling = model.Poll();
        await model.Pause();
        audio.DelayedStatus.SetResult(new AudioStatus { AbiVersion = 1, Phase = 2, SampleRate = 48000, PositionFrames = 400 });
        await polling; audio.DelayedStatus = null;
        Check(!model.IsPlaying && model.Position != 400.0 / 48000);
        await model.Stop(); Check(model.Position == 0 && !model.IsPlaying && session.SourceRenders == 10);
        audio.Rate = 44100;
        await model.PlayProject(); Check(!model.IsSourceContext && !model.IsPlaying && session.ProjectRenders == 1 && model.Status == "Native CPR project playback is unavailable.");
        audio.Rate = 48000; await model.AuditionSource();
        await model.Seek(0.75 / 48000); Check(audio.LastSeek == 1 && model.IsPlaying);
        await model.Seek(0.5 / 48000); Check(audio.LastSeek == 1);
        await model.Seek(0.49 / 48000); Check(audio.LastSeek == 0);
        plays = audio.Plays;
        await model.Seek(1); Check(audio.LastSeek == 480 && !model.IsPlaying && audio.Plays == plays);
        await model.Play(); Check(audio.LastSeek == 0 && model.IsPlaying);
        await model.AttachSourceMedia("synthetic-media.wav"); Check(!model.IsSourceContext && !model.IsPlaying && model.State.Revision == 2);
        return checks;
    }
    private sealed class ControlSession(ProjectView project) : ISessionClient
    {
        private readonly SessionState state = new() { Revision = 1, Project = project, Selection = new() { TrackID = "track", ClipID = EventID } };
        public int SourceRenders, ProjectRenders;
        public bool WrongMediaReceipt, FailSourceRender;
        public object[] ModuleReceipt() => [];
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
        public Task<SessionResponse> Send(SessionRequest request)
        {
            if (request.Command == "attachSourceMedia") state.Revision++;
            var response = new SessionResponse { Protocol = 1, Id = request.Id, Ok = true,
                State = new() { Revision = state.Revision, Project = project, Selection = state.Selection } };
            if (request.Command == "render") { ProjectRenders++; response.Ok = false; response.Error = new() { Message = "Native CPR project playback is unavailable." }; }
            if (request.Command == "renderSourceEvent")
            {
                SourceRenders++;
                if (FailSourceRender) { response.Ok = false; response.Error = new() { Message = "Source changed outside the session." }; }
                else
                {
                    var bytes = Wave(); File.WriteAllBytes(request.Path!, bytes);
                    response.Render = new() { Kind = "sourceEvent", EventID = EventID, SourceSHA256 = SourceHash,
                        MediaSHA256 = WrongMediaReceipt ? new string('c', 64) : MediaHash, Path = request.Path!, Revision = state.Revision,
                        SampleRate = 48000, Frames = 480, Channels = 2, WavBytes = (ulong)bytes.Length, Sha256 = Convert.ToHexString(SHA256.HashData(bytes)) };
                }
            }
            return Task.FromResult(response);
        }
        private static byte[] Wave()
        {
            var bytes = new byte[44 + 480 * 8];
            Encoding.ASCII.GetBytes("RIFF").CopyTo(bytes, 0); BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(4), (uint)bytes.Length - 8);
            Encoding.ASCII.GetBytes("WAVEfmt ").CopyTo(bytes, 8); BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(16), 16);
            BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(20), 3); BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(22), 2);
            BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(24), 48000); BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(28), 384000);
            BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(32), 8); BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(34), 32);
            Encoding.ASCII.GetBytes("data").CopyTo(bytes, 36); BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(40), 480 * 8);
            return bytes;
        }
    }
    private sealed class ControlAudio : IAudioOutput
    {
        public uint Rate = 48000, SourceRate;
        public int FormatCalls, SourceCopies, Plays, Stops;
        public ulong LastSeek;
        public TaskCompletionSource<AudioStatus>? DelayedStatus;
        public Task<DeviceFormat> Format() { FormatCalls++; return Task.FromResult(new DeviceFormat { SampleRate = Rate, Channels = 2, Float32 = 1 }); }
        public Task<AudioStatus> Status() => DelayedStatus?.Task ?? Task.FromResult(new AudioStatus { AbiVersion = 1, SampleRate = SourceRate, PositionFrames = LastSeek });
        public Task SetSource(LoadedSnapshot source) { SourceCopies++; SourceRate = source.SampleRate; return Task.CompletedTask; }
        public Task Play() { Plays++; return Task.CompletedTask; }
        public Task Pause() => Task.CompletedTask;
        public Task Stop() { Stops++; return Task.CompletedTask; }
        public Task Seek(ulong frame) { LastSeek = frame; return Task.CompletedTask; }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
