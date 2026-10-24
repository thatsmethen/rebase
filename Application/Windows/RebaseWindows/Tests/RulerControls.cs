using Rebase.Windows;

static class RulerControls
{
    public static async Task<int> Run()
    {
        int checks = 0;
        void Check(bool value) { checks++; if (!value) throw new Exception("Ruler control " + checks + " failed."); }
        void Reject(Action action) { checks++; try { action(); } catch (InvalidDataException) { return; } throw new Exception("Malformed ruler accepted."); }
        var request = new RulerRequest(1, 24, 32);
        Snapshot(1, 32).Validate(request); Check(true);
        var bad = Snapshot(1, 32); bad.Revision = 2; Reject(() => bad.Validate(request));
        bad = Snapshot(1, 32); bad.Duration = 25; Reject(() => bad.Validate(request));
        bad = Snapshot(1, 32); bad.PixelsPerSecond = 33; Reject(() => bad.Validate(request));
        bad = Snapshot(1, 32); bad.Ticks[1].Seconds = double.NaN; Reject(() => bad.Validate(request));
        bad = Snapshot(1, 32); bad.Ticks[1].Seconds = 25; Reject(() => bad.Validate(request));
        bad = Snapshot(1, 32); bad.Ticks[1].Seconds = 0; Reject(() => bad.Validate(request));
        bad = Snapshot(1, 32); bad.Ticks[1].Label = "2<script>"; Reject(() => bad.Validate(request));
        bad = Snapshot(1, 32); bad.Ticks[0].Bar = false; Reject(() => bad.Validate(request));
        bad = Snapshot(1, 32); bad.Ticks = []; Reject(() => bad.Validate(request));
        bad = Snapshot(1, 32); bad.Ticks = new RulerTick[8193]; Reject(() => bad.Validate(request));
        bad = Snapshot(1, 32); bad.Ticks[1] = null!; Reject(() => bad.Validate(request));

        var helper = new RulerSession();
        await using var model = new StudioViewModel(helper, new UnusedAudio());
        await model.Open("first-document", false, false);
        model.SetRulerViewport(32, 24);
        await helper.FirstRequested.Task.WaitAsync(TimeSpan.FromSeconds(5));
        await model.Command("setTempo", value: 120);
        model.SetRulerViewport(100, 24);
        helper.FirstReply.SetResult(new() { Protocol = 1, Ok = true, State = new() { Revision = 1 }, Ruler = Snapshot(1, 32) });
        await Until(() => model.Ruler?.Revision == 2 && model.Ruler.PixelsPerSecond == 100);
        Check(model.State.Revision == 2 && model.Project!.Tempo == 120 && helper.Requests == 2);
        Check(model.Ruler!.Ticks[1].Seconds == 2.5); // Display projection is retained, never recalculated from Project.Tempo.
        helper.CorruptNext = true;
        model.SetRulerViewport(101, 24);
        await Until(() => model.RulerError is not null);
        Check(model.Ruler is null && model.State.Revision == 2 && model.Project!.Tempo == 120);
        model.SetRulerViewport(101, 24); await Task.Delay(60);
        Check(helper.Requests == 3); // A failed key does not spin/retry forever.
        model.SetRulerViewport(102, 24);
        await Until(() => model.Ruler?.PixelsPerSecond == 102);
        Check(helper.Requests == 4 && model.RulerError is null);
        await model.Command("setTempo", value: 96);
        Check(model.Ruler is null); // Old musical positions disappear on any new revision.
        model.SetRulerViewport(102, 24);
        await Until(() => model.Ruler?.Revision == 3);
        Check(model.Project!.Tempo == 96 && helper.Requests == 5);
        return checks;
    }
    private static RulerSnapshot Snapshot(ulong revision, double pixels) => new() { Revision = revision, Duration = 24, PixelsPerSecond = pixels,
        Ticks = [new() { Seconds = 0, Bar = true, Label = "1" }, new() { Seconds = 2.5, Bar = true, Label = "2" }] };
    private static async Task Until(Func<bool> condition)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        while (!condition()) await Task.Delay(10, timeout.Token);
    }
    private sealed class RulerSession : ISessionClient
    {
        public readonly TaskCompletionSource<bool> FirstRequested = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public readonly TaskCompletionSource<SessionResponse> FirstReply = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public int Requests;
        public bool CorruptNext;
        private ulong revision;
        private double tempo = 96;
        public object[] ModuleReceipt() => [];
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
        private SessionState State => new() { Revision = revision, Project = new() { Id = "project", Tempo = tempo, SampleRate = 48000 } };
        public Task<SessionResponse> Send(SessionRequest request)
        {
            if (request.Command == "ruler")
            {
                Requests++;
                if (Requests == 1) { FirstRequested.TrySetResult(true); return FirstReply.Task; }
                var ruler = Snapshot(revision, request.Value!.Value);
                if (CorruptNext) { ruler.Ticks[1].Seconds = -1; CorruptNext = false; }
                return Task.FromResult(new SessionResponse { Protocol = 1, Ok = true, State = State, Ruler = ruler });
            }
            revision++;
            if (request.Command == "setTempo") tempo = request.Value!.Value;
            return Task.FromResult(new SessionResponse { Protocol = 1, Ok = true, State = State });
        }
    }
    private sealed class UnusedAudio : IAudioOutput
    {
        private static Exception Unexpected() => new Exception("Ruler projection must not access an audio device.");
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
