using System.Buffers.Binary;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Rebase.Windows;

// Authored host controls. These fakes exercise host decisions, not SoXR or a
// device. Native conversion and endpoint behavior have separate controls.
static class PlaybackRateControls
{
    private const string EventID = "00000000-0000-4000-8000-000000000011";
    private static readonly string SourceHash = new('a', 64), MediaHash = new('b', 64);

    public static async Task<int> Run()
    {
        int checks = 0;
        void Check(bool value) { checks++; if (!value) throw new Exception("Playback rate control " + checks + " failed."); }
        void Reject(AudioRateInfo info, LoadedSnapshot source)
        {
            checks++;
            try { info.ValidateForSource(source); }
            catch (InvalidDataException) { return; }
            throw new Exception("Malformed native rate receipt accepted.");
        }
        var source = new LoadedSnapshot(new float[8820], 44100, 4410);
        NativeAudio.ValidateSource(source); Check(true);
        NativeAudio.ValidateSource(new LoadedSnapshot([0, -0.0f, float.MaxValue, -float.MaxValue], 8000, 2)); Check(true);
        NativeAudio.ValidateSource(new LoadedSnapshot([0, 0], 192000, 1)); Check(true);
        foreach (var malformed in new LoadedSnapshot?[] {
            null, source with { Samples = null! }, source with { Frames = 0 }, source with { Frames = 32_000_001 },
            source with { Frames = ulong.MaxValue }, source with { SampleRate = 7999 }, source with { SampleRate = 192001 },
            source with { Samples = [] }, source with { Samples = new float[8819] }, source with { Samples = new float[8821] },
            new([float.NaN, 0], 48000, 1), new([0, float.PositiveInfinity], 48000, 1), new([float.NegativeInfinity, 0], 48000, 1) })
        {
            checks++;
            try { NativeAudio.ValidateSource(malformed); throw new Exception("Malformed managed audio source accepted."); }
            catch (InvalidDataException) { }
        }
        // The production adapter must reject an unsafe frame count without
        // loading a native DLL or invoking a device. This runs on macOS too.
        await using (var native = new NativeAudio())
        {
            checks++;
            try { await native.SetSource(source with { Frames = ulong.MaxValue }); throw new Exception("Unsafe source reached native audio."); }
            catch (InvalidDataException) { }
        }
        var valid = new AudioRateInfo { AbiVersion = 1, SourceRate = 44100, EndpointRate = 48000,
            Converted = 1, SourceFrames = 4410, EndpointFrames = 4800, SoxrRecipe = 6 };
        Check(Marshal.SizeOf<AudioRateInfo>() == 56 && Marshal.OffsetOf<AudioRateInfo>(nameof(AudioRateInfo.SourceFrames)).ToInt64() == 16 &&
              Marshal.OffsetOf<AudioRateInfo>(nameof(AudioRateInfo.SoxrRecipe)).ToInt64() == 48);
        valid.ValidateForSource(source); Check(true);
        foreach (var mutate in new Func<AudioRateInfo, AudioRateInfo>[] {
            r => { r.AbiVersion = 2; return r; }, r => { r.Reserved = 1; return r; },
            r => { r.SourceRate = 48000; return r; }, r => { r.SourceFrames--; return r; },
            r => { r.EndpointRate = 0; return r; }, r => { r.EndpointRate = 192001; return r; },
            r => { r.EndpointFrames = 0; return r; }, r => { r.EndpointFrames = 4801; return r; },
            r => { r.EndpointFrames = 32_000_001; return r; }, r => { r.Converted = 0; return r; },
            r => { r.Converted = 2; return r; }, r => { r.SoxrRecipe = 0; return r; },
            r => { r.EndpointPositionFrames = 1; return r; }, r => { r.EndpointSubmittedFrames = 1; return r; } })
            Reject(mutate(valid), source);
        Reject(valid, source with { SampleRate = 0 });
        var identity = valid; identity.EndpointRate = identity.SourceRate; identity.EndpointFrames = identity.SourceFrames;
        identity.Converted = 0; identity.SoxrRecipe = 0;
        identity.ValidateForSource(source); Check(true);
        identity.EndpointFrames--; Reject(identity, source);

        var session = new ControlSession(); var audio = new ControlAudio();
        await using (var model = new StudioViewModel(session, audio))
        {
            await model.Open("authored-rate-control", false, false);
            var before = JsonSerializer.Serialize(model.State, ProtocolJson.Options);
            await model.AuditionSource();
            Check(model.IsPlaying && audio.SourceRate == 44100 && audio.EndpointRate == 48000 && session.SourceRenders == 1);
            Check(model.PlaybackRateInfo is { SourceRate: 44100, EndpointRate: 48000, Converted: 1, SourceFrames: 4410, EndpointFrames: 4800 });
            Check(model.Status.Contains("44100 → 48000 Hz (converted)", StringComparison.Ordinal));
            Check(JsonSerializer.Serialize(model.State, ProtocolJson.Options) == before);
            // No UI poll has observed this device position. Immediate resume
            // must use the frozen cursor, not the prior displayed zero.
            audio.FrozenPosition = 2205;
            await model.Pause();
            Check(!model.IsPlaying && model.Position == 0.05 && session.SourceRenders == 1);
            await model.Play();
            Check(model.IsPlaying && session.SourceRenders == 2 && audio.LastSeek == 2205 && audio.SourceCopies == 2);
            await model.Seek(0.025);
            Check(model.IsPlaying && session.SourceRenders == 3 && audio.LastSeek == 1103); // Source-frame half-up policy.
            await model.Seek(5);
            Check(!model.IsPlaying && audio.LastSeek == 4410 && model.Position == 0.1);
            await model.Play(); Check(model.IsPlaying && audio.LastSeek == 0);
            var late = new TaskCompletionSource<AudioStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
            audio.NextStatus = late; var polling = model.Poll();
            audio.FrozenPosition = 882;
            await model.Pause();
            late.SetResult(new AudioStatus { AbiVersion = 1, Phase = 2, SampleRate = 44100, TotalFrames = 4410,
                SubmittedFrames = 4410, PositionFrames = 4000 });
            await polling;
            Check(!model.IsPlaying && model.Position == 0.02);
            await model.Play(); Check(audio.LastSeek == 882);
            var plays = audio.Plays; var copies = audio.SourceCopies;
            session.WrongMedia = true;
            await model.Play();
            Check(!model.IsPlaying && audio.Plays == plays && audio.SourceCopies == copies && model.PlaybackRateInfo is null);
            session.WrongMedia = false; session.SourceChanged = true;
            await model.Seek(0.01);
            Check(audio.Plays == plays && audio.SourceCopies == copies && model.Status == "Source changed outside the session.");
            session.SourceChanged = false;
            await model.Play(); Check(model.IsPlaying);
            await model.AttachSourceMedia("authored-media.wav");
            Check(!model.IsPlaying && !model.IsSourceContext && model.PlaybackRateInfo is null && model.State.Revision == 2);

            // Project seek and pause remain in the rendered project's units,
            // even when the endpoint operates at a different rate.
            audio.EndpointRate = 44100;
            await model.PlayProject();
            Check(model.IsPlaying && !model.IsSourceContext && audio.SourceRate == 48000 && session.ProjectRenders == 1);
            await model.Seek(0.025); Check(audio.LastSeek == 1200);
            audio.FrozenPosition = 2400;
            await model.Pause(); Check(model.Position == 0.05);
            copies = audio.SourceCopies;
            var beforeResume = new TaskCompletionSource<AudioStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
            audio.NextStatus = beforeResume; var pausedPolling = model.Poll();
            await model.Play(); Check(model.IsPlaying && audio.SourceCopies == copies && audio.LastSeek == 1200);
            beforeResume.SetResult(new AudioStatus { AbiVersion = 1, Phase = 3, SampleRate = 48000, TotalFrames = 4800,
                SubmittedFrames = 4800, PositionFrames = 2400 });
            await pausedPolling; Check(model.IsPlaying);
            // A failed frozen-position read invalidates the snapshot. A later
            // user retry must rebuild; it cannot resume an unverified cursor.
            audio.FailStatus = true;
            await model.Pause();
            Check(!model.IsPlaying && model.PlaybackRateInfo is null && model.Position == 0);
            audio.FailStatus = false;
            await model.Play(); Check(model.IsPlaying && audio.SourceCopies == copies + 1);
            audio.FrozenPosition = 4800;
            await model.Pause(); Check(!model.IsPlaying && model.Position == 0.1 && model.Status.StartsWith("Finished", StringComparison.Ordinal));
            await model.Play(); Check(model.IsPlaying && audio.LastSeek == 0);
        }

        foreach (var badFormat in new DeviceFormat[] {
            new() { SampleRate = 48000, Channels = 1, Float32 = 1 },
            new() { SampleRate = 48000, Channels = 2, Float32 = 0 },
            new() { SampleRate = 7999, Channels = 2, Float32 = 1 },
            new() { SampleRate = 192001, Channels = 2, Float32 = 1 } })
        {
            var fakeSession = new ControlSession(); var fakeAudio = new ControlAudio { FormatOverride = badFormat };
            await using var model = new StudioViewModel(fakeSession, fakeAudio);
            await model.Open("authored-format-control", false, false); await model.PlayProject();
            Check(!model.IsPlaying && fakeSession.ProjectRenders == 0 && fakeAudio.SourceCopies == 0 && fakeAudio.Plays == 0);
        }
        foreach (var code in new[] { 3, 4, 9, 10, 11, 12 })
        {
            var fakeSession = new ControlSession(); var fakeAudio = new ControlAudio { SourceFailure = code };
            await using var model = new StudioViewModel(fakeSession, fakeAudio);
            await model.Open("authored-failure-control", false, false); await model.AuditionSource();
            Check(!model.IsPlaying && model.PlaybackRateInfo is null && fakeAudio.Plays == 0 && fakeSession.SourceRenders == 1);
        }
        foreach (var invalidReceipt in new[] { false, true })
        {
            var fakeAudio = new ControlAudio { FailRateInfo = !invalidReceipt, WrongRateInfo = invalidReceipt };
            await using var model = new StudioViewModel(new ControlSession(), fakeAudio);
            await model.Open("authored-receipt-control", false, false); await model.AuditionSource();
            Check(!model.IsPlaying && model.PlaybackRateInfo is null && fakeAudio.Plays == 0 && fakeAudio.Stops == 1);
        }
        // Endpoint discovery is advisory: source installation owns the actual
        // current endpoint, which can legitimately change between the calls.
        var changedDevice = new ControlAudio { FormatOverride = new() { SampleRate = 96000, Channels = 2, Float32 = 1 }, EndpointRate = 48000 };
        await using (var model = new StudioViewModel(new ControlSession(), changedDevice))
        {
            await model.Open("authored-device-change", false, false); await model.AuditionSource();
            Check(model.IsPlaying && model.PlaybackRateInfo?.EndpointRate == 48000 && !model.Status.Contains("96000", StringComparison.Ordinal));
        }
        var endAudio = new ControlAudio { EndpointRate = 8000, QuantizedEndFrom = 4408 };
        await using (var model = new StudioViewModel(new ControlSession(), endAudio))
        {
            await model.Open("authored-rounded-eof", false, false); await model.AuditionSource();
            var plays = endAudio.Plays;
            await model.Seek(4409.0 / 44100);
            Check(!model.IsPlaying && model.Position == 0.1 && endAudio.LastSeek == 4409 && endAudio.Plays == plays);
            await model.Play(); Check(model.IsPlaying && endAudio.LastSeek == 0 && endAudio.Plays == plays + 1);
            await model.Stop();
            await model.SeekProject(4799.0 / 48000);
            endAudio.QuantizedEndFrom = 4797; plays = endAudio.Plays;
            await model.PlayProject();
            Check(!model.IsPlaying && !model.IsSourceContext && model.Position == 0.1 && endAudio.Plays == plays);
            await model.Play(); Check(model.IsPlaying && endAudio.LastSeek == 0);
        }
        return checks;
    }

    private sealed class ControlAudio : IAudioOutput
    {
        public uint EndpointRate = 48000, SourceRate;
        public ulong Frames, LastSeek;
        public ulong? FrozenPosition;
        public ulong? QuantizedEndFrom;
        private ulong position;
        private uint phase;
        public int SourceCopies, Plays, Stops, SourceFailure;
        public bool FailStatus, FailRateInfo, WrongRateInfo;
        public DeviceFormat? FormatOverride;
        public TaskCompletionSource<AudioStatus>? NextStatus;
        public Task<DeviceFormat> Format() => Task.FromResult(FormatOverride ?? new() { SampleRate = EndpointRate, Channels = 2, Float32 = 1 });
        public Task SetSource(LoadedSnapshot source)
        {
            if (SourceFailure != 0) throw new NativeAudioException(SourceFailure, "Authored native setup failure.");
            SourceCopies++; SourceRate = source.SampleRate; Frames = source.Frames; position = 0; phase = 1;
            return Task.CompletedTask;
        }
        public Task<AudioRateInfo> RateInfo()
        {
            if (FailRateInfo) throw new IOException("Authored rate receipt failure.");
            return Task.FromResult(new AudioRateInfo { AbiVersion = 1, SourceRate = WrongRateInfo ? 8000 : SourceRate,
                EndpointRate = EndpointRate, Converted = SourceRate == EndpointRate ? 0u : 1u,
                SourceFrames = Frames, EndpointFrames = (Frames * EndpointRate + SourceRate - 1) / SourceRate,
                SoxrRecipe = SourceRate == EndpointRate ? 0u : 6u });
        }
        public Task<AudioStatus> Status()
        {
            if (NextStatus is { } delayed) { NextStatus = null; return delayed.Task; }
            if (FailStatus) throw new IOException("Authored frozen cursor failure.");
            return Task.FromResult(new AudioStatus { AbiVersion = 1, Phase = phase, SampleRate = SourceRate,
                TotalFrames = Frames, SubmittedFrames = Frames, PositionFrames = position });
        }
        public Task Play() { Plays++; phase = 2; return Task.CompletedTask; }
        public Task Pause() { position = FrozenPosition ?? position; phase = position == Frames ? 4u : 3u; return Task.CompletedTask; }
        public Task Stop() { Stops++; phase = 1; position = 0; return Task.CompletedTask; }
        public Task Seek(ulong frame)
        {
            LastSeek = frame;
            position = QuantizedEndFrom is { } limit && frame >= limit ? Frames : frame;
            phase = position == Frames ? 4u : phase == 2 ? 2u : 1u;
            return Task.CompletedTask;
        }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }

    private sealed class ControlSession : ISessionClient
    {
        private ulong revision = 1;
        public int SourceRenders, ProjectRenders;
        public bool WrongMedia, SourceChanged;
        private readonly ProjectView project = JsonSerializer.Deserialize<ProjectView>($$$"""
            {"id":"project","name":"Authored playback control","sampleRate":48000,"tempo":120,"tempoMap":[],"signatureMap":[],
             "tracks":[{"id":"track","name":"Control","clips":[{"id":"ordinary","position":0,"duration":0.1}],
             "unresolvedAudioEvents":[{"id":"{{{EventID}}}","name":"Source event","sourceSHA256":"{{{SourceHash}}}","files":[{"object":{"identityOffset":1024}}]}]}],
             "cprMediaAttachments":[{"association":"user-selected","sourceSHA256":"{{{SourceHash}}}","sourceFileIdentity":1024,"mediaSHA256":"{{{MediaHash}}}"}]}
            """, ProtocolJson.Options)!;
        public object[] ModuleReceipt() => [];
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
        public Task<SessionResponse> Send(SessionRequest request)
        {
            if (request.Command == "attachSourceMedia") revision++;
            var response = new SessionResponse { Protocol = 1, Id = request.Id, Ok = true,
                State = new() { Revision = revision, Project = project, Selection = new() { TrackID = "track", ClipID = EventID } } };
            if (request.Command is "renderSourceEvent" or "render")
            {
                var isSource = request.Command == "renderSourceEvent";
                if (isSource) SourceRenders++; else ProjectRenders++;
                if (isSource && SourceChanged) { response.Ok = false; response.Error = new() { Message = "Source changed outside the session." }; return Task.FromResult(response); }
                uint rate = isSource ? 44100u : 48000u; uint frames = rate / 10;
                var wave = Wave(rate, frames); File.WriteAllBytes(request.Path!, wave);
                response.Render = new() { Kind = isSource ? "sourceEvent" : "project", Path = request.Path!, Revision = revision,
                    EventID = isSource ? EventID : null, SourceSHA256 = isSource ? SourceHash : null,
                    MediaSHA256 = isSource ? WrongMedia ? new('c', 64) : MediaHash : null,
                    SampleRate = rate, Frames = frames, Channels = 2, WavBytes = (ulong)wave.Length,
                    Sha256 = Convert.ToHexString(SHA256.HashData(wave)) };
            }
            return Task.FromResult(response);
        }
        private static byte[] Wave(uint rate, uint frames)
        {
            var bytes = new byte[44 + frames * 8];
            Encoding.ASCII.GetBytes("RIFF").CopyTo(bytes, 0); BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(4), (uint)bytes.Length - 8);
            Encoding.ASCII.GetBytes("WAVEfmt ").CopyTo(bytes, 8); BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(16), 16);
            BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(20), 3); BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(22), 2);
            BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(24), rate); BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(28), rate * 8);
            BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(32), 8); BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(34), 32);
            Encoding.ASCII.GetBytes("data").CopyTo(bytes, 36); BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(40), frames * 8);
            return bytes;
        }
    }
}
