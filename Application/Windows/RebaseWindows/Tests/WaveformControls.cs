using Rebase.Windows;

static class WaveformControls
{
    public static async Task<int> Run()
    {
        int checks = 0;
        void Check(bool value) { checks++; if (!value) throw new Exception("Waveform control " + checks + " failed."); }
        void Reject(Action action) { checks++; try { action(); } catch (InvalidDataException) { return; } throw new Exception("Malformed waveform accepted."); }
        var clip = new ClipView { Id = "clip", MediaPath = "Media/control.wav", Position = 2, SourceOffset = 0.25, Duration = 0.002 };
        WaveformSnapshot Valid() => new() { Revision = 1, ClipID = "clip", SampleRate = 8000, SourceStartFrame = 2000, SourceFrames = 16, MediaSHA256 = new string('a', 64), Peaks = new float[16] };
        Valid().Validate(clip, 1); Check(true);
        Reject(() => Valid().Validate(clip, 2));
        var bad = Valid(); bad.SourceStartFrame++; Reject(() => bad.Validate(clip, 1));
        bad = Valid(); bad.SourceFrames = 17; bad.Peaks = new float[17]; Reject(() => bad.Validate(clip, 1));
        bad = Valid(); bad.Peaks[1] = -0.1f; Reject(() => bad.Validate(clip, 1));
        bad = Valid(); bad.Peaks[1] = float.NaN; Reject(() => bad.Validate(clip, 1));
        bad = Valid(); bad.MediaSHA256 = "not-a-hash"; Reject(() => bad.Validate(clip, 1));
        bad = Valid(); bad.SampleRate = double.PositiveInfinity; Reject(() => bad.Validate(clip, 1));
        bad = Valid(); bad.ClipID = "deleted"; Reject(() => bad.Validate(clip, 1));
        bad = Valid(); bad.SourceFrames = 0; bad.Peaks = []; Reject(() => bad.Validate(clip, 1));

        var session = new WaveformSession();
        await using var model = new StudioViewModel(session, new UnusedAudio());
        await model.Open("first-document", false, false);
        await session.FirstRequested.Task.WaitAsync(TimeSpan.FromSeconds(5));
        await model.Command("moveClip", clipID: "clip", value: 7);
        session.FirstReply.SetResult(session.ResponseFor(1, 2, 0.002));
        await Until(() => model.WaveformPeaks.Count == 1);
        Check(model.State.Revision == 2 && model.Project!.Tracks[0].Clips[0].Position == 7 && session.Requests == 2);
        var retained = model.WaveformPeaks["clip"];
        await model.Command("setGain", trackID: "track", value: -6);
        await Task.Delay(60);
        Check(session.Requests == 2 && ReferenceEquals(retained, model.WaveformPeaks["clip"]));
        await model.Command("trimClip", clipID: "clip", value: 7.001);
        await Until(() => model.WaveformPeaks.TryGetValue("clip", out var peaks) && peaks.Length == 8);
        Check(session.Requests == 3);
        await model.Save("new-package.rebaseproj");
        await Until(() => session.Requests == 4 && model.WaveformPeaks.Count == 1);
        Check(!ReferenceEquals(retained, model.WaveformPeaks["clip"]));
        await model.Command("deleteEvent", clipID: "clip");
        Check(model.WaveformPeaks.Count == 0);
        return checks;
    }
    private static async Task Until(Func<bool> condition)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        while (!condition()) await Task.Delay(10, timeout.Token);
    }
    private sealed class WaveformSession : ISessionClient
    {
        public readonly TaskCompletionSource<bool> FirstRequested = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public readonly TaskCompletionSource<SessionResponse> FirstReply = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public int Requests;
        private ulong revision;
        private double position = 2, duration = 0.002;
        private bool deleted;
        public object[] ModuleReceipt() => [];
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
        private SessionState State(ulong rev, double pos, double length) => new() { Revision = rev,
            Selection = new() { TrackID = "track", ClipID = deleted ? null : "clip" },
            Project = new() { Id = "project", SampleRate = 44100, Tracks = [new() { Id = "track", Clips = deleted ? [] : [new() { Id = "clip", MediaPath = "Media/control.wav", Position = pos, Duration = length, SourceOffset = 0.25 }] }] } };
        public SessionResponse ResponseFor(ulong rev, double pos, double length) => new() { Protocol = 1, Ok = true, State = State(rev, pos, length),
            Waveform = new() { Revision = rev, ClipID = "clip", SampleRate = 8000, SourceStartFrame = 2000, SourceFrames = (ulong)(length * 8000),
                MediaSHA256 = new string('a', 64), Peaks = Enumerable.Repeat(0.25f, (int)(length * 8000)).ToArray() } };
        public Task<SessionResponse> Send(SessionRequest request)
        {
            if (request.Command == "waveform")
            {
                Requests++;
                if (Requests == 1) { FirstRequested.TrySetResult(true); return FirstReply.Task; }
                return Task.FromResult(ResponseFor(revision, position, duration));
            }
            revision++;
            if (request.Command == "moveClip") position = request.Value!.Value;
            if (request.Command == "trimClip") duration = 0.001;
            if (request.Command == "deleteEvent") deleted = true;
            return Task.FromResult(new SessionResponse { Protocol = 1, Ok = true, State = State(revision, position, duration) });
        }
    }
    private sealed class UnusedAudio : IAudioOutput
    {
        private static Exception Unexpected() => new Exception("Waveform background work must not access an audio device.");
        public Task<DeviceFormat> Format() => throw Unexpected();
        public Task<AudioRateInfo> RateInfo() => throw Unexpected();
        public Task<AudioStatus> Status() => throw Unexpected();
        public Task SetSource(LoadedSnapshot source) => throw Unexpected();
        public Task Play() => throw Unexpected();
        public Task Pause() => throw Unexpected();
        public Task Stop() => throw Unexpected();
        public Task Seek(ulong frame) => throw Unexpected();
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
