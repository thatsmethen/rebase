using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using System.Windows;
using System.Windows.Automation.Peers;
using System.Windows.Automation.Provider;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace Rebase.Windows;

public partial class MainWindow
{
    private async Task<object> RunSourceStreamSmoke(string artifactRoot, List<string> checks,
        Action<string> setStage, CancellationToken cancellation)
    {
        var fixtureRoot = Environment.GetEnvironmentVariable("REBASE_SMOKE_SOURCE_STREAM_FIXTURE")
            ?? throw new InvalidOperationException("The authored long-source fixture was not supplied.");
        var fixtureBytes = await File.ReadAllBytesAsync(Path.Combine(fixtureRoot, "expected.json"), cancellation);
        using var fixture = JsonDocument.Parse(fixtureBytes);
        var records = new List<object>();
        object? capture = null;
        SourceAudioWindow? dialog = null;
        string Hash(byte[] bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));
        string StateHash() => Hash(JsonSerializer.SerializeToUtf8Bytes(model.State, ProtocolJson.Options));
        void Check(bool okay, string name)
        {
            setStage(name);
            if (!okay) throw new InvalidOperationException(name + ": " + (dialog?.Message ?? model.Status));
            checks.Add(name);
        }
        async Task Idle()
        {
            using var limit = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
            limit.CancelAfter(TimeSpan.FromSeconds(120));
            do
            {
                await Dispatcher.InvokeAsync(() => { UpdateLayout(); dialog?.UpdateLayout(); }, DispatcherPriority.ApplicationIdle);
                if (!model.Busy && dialog?.Working != true && (!openingSourceAudio || activeSourceAudio is not null)) return;
                await Task.Delay(20, limit.Token);
            } while (true);
        }
        async Task Invoke(Button button)
        {
            if (!button.IsVisible || !button.IsEnabled) throw new InvalidOperationException("Long-source action is unavailable: " + button.Content);
            ((IInvokeProvider)new ButtonAutomationPeer(button).GetPattern(PatternInterface.Invoke)).Invoke();
            await Idle();
        }
        async Task SelectTrackMode()
        {
            var index = Array.FindIndex(SourceAuditionMode.All, row => row.Id == SourceAuditionMode.CompleteTrack);
            var list = dialog!.Modes; list.ScrollIntoView(list.Items[index]); list.UpdateLayout();
            var peer = new ListBoxAutomationPeer(list);
            var item = peer.GetChildren()?.Select(child => child.GetPattern(PatternInterface.SelectionItem)).OfType<ISelectionItemProvider>().ElementAt(index)
                ?? throw new InvalidOperationException("The complete-track mode has no accessible list item.");
            item.Select(); await Idle();
        }
        async Task<object> Capture()
        {
            await Idle(); var content = (FrameworkElement)dialog!.Content; var dpi = VisualTreeHelper.GetDpi(content);
            var width = checked((int)Math.Ceiling(content.ActualWidth * dpi.DpiScaleX));
            var height = checked((int)Math.Ceiling(content.ActualHeight * dpi.DpiScaleY));
            var bitmap = new RenderTargetBitmap(width, height, dpi.PixelsPerInchX, dpi.PixelsPerInchY, PixelFormats.Pbgra32); bitmap.Render(content);
            var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
            const string name = "native-source-stream-visual.png";
            var path = Path.Combine(artifactRoot, name); using (var stream = File.Create(path)) encoder.Save(stream);
            var controls = new List<object>();
            foreach (var (controlName, element) in new (string, FrameworkElement)[] {
                ("modes",dialog.Modes),("position",dialog.PositionInput),("seek",dialog.SeekButton),
                ("refresh",dialog.RefreshButton),("export",dialog.ExportButton),("play",dialog.PlayButton),
                ("pause",dialog.PauseButton),("stop",dialog.StopButton),("close",dialog.CloseButton) })
            {
                var point = element.TransformToAncestor(content).Transform(new Point());
                if (!element.IsVisible || element.ActualWidth <= 0 || element.ActualHeight <= 0 || point.X < -0.5 || point.Y < -0.5 ||
                    point.X + element.ActualWidth > content.ActualWidth + 0.5 || point.Y + element.ActualHeight > content.ActualHeight + 0.5)
                    throw new InvalidOperationException("A source-stream control is outside the client capture: " + controlName);
                controls.Add(new { name = controlName, x = point.X, y = point.Y, width = element.ActualWidth, height = element.ActualHeight, enabled = element.IsEnabled });
            }
            return new { file = name, sha256 = Hash(await File.ReadAllBytesAsync(path, cancellation)),
                bounds = new { outer_width_dip = dialog.ActualWidth, outer_height_dip = dialog.ActualHeight,
                    width_dip = content.ActualWidth, height_dip = content.ActualHeight, dpi_scale_x = dpi.DpiScaleX, dpi_scale_y = dpi.DpiScaleY,
                    pixel_width = width, pixel_height = height }, controls, selected_mode = dialog.SelectedMode,
                details = dialog.Details, message = dialog.Message, frame_excluded = true };
        }
        try
        {
            foreach (var row in fixture.RootElement.GetProperty("cases").EnumerateArray())
            {
                var name = row.GetProperty("name").GetString()!;
                var anchor = row.GetProperty("anchorID").GetString()!;
                var expected = row.GetProperty("modes").EnumerateArray().Single(mode => mode.GetProperty("mode").GetString() == SourceAuditionMode.CompleteTrack);
                var total = expected.GetProperty("totalFrames").GetUInt64(); var rate = expected.GetProperty("sampleRate").GetUInt32();
                setStage("source-stream-" + name + "-open");
                await model.Open(Path.Combine(fixtureRoot, row.GetProperty("root").GetString()!.Replace('/', Path.DirectorySeparatorChar)), true, true);
                await model.Command("selectClip", clipID: anchor); await Idle();
                var before = StateHash();
                await Invoke(SourceAudioButton); dialog = activeSourceAudio ?? throw new InvalidOperationException("Source Audio did not open.");
                dialog.Width = dialog.MinWidth; dialog.Height = dialog.MinHeight; await SelectTrackMode();
                var available = model.SourceInspection!.Modes.Single(mode => mode.Mode == SourceAuditionMode.CompleteTrack);
                Check(available.Available && available.LiveAvailable && !available.SnapshotExportAvailable && available.Frames == total &&
                    total > 32_000_000 && available.SampleRate == rate && dialog.PlayButton.IsEnabled && !dialog.ExportButton.IsEnabled &&
                    !string.IsNullOrWhiteSpace(available.SnapshotExportReason) && before == StateHash(), "source-stream-" + name + "-availability");
                var availability = new { available = available.Available, live_available = available.LiveAvailable,
                    snapshot_export_available = available.SnapshotExportAvailable, snapshot_export_reason = available.SnapshotExportReason,
                    sample_rate = available.SampleRate, total_frames = available.Frames,
                    play_enabled = dialog.PlayButton.IsEnabled, export_enabled = dialog.ExportButton.IsEnabled };
                var requestsBefore = model.HelperRequestCounts();
                var admissions = new List<object>(); var generations = new HashSet<string>();
                void Admission(string action, ulong expectedStart)
                {
                    var admitted = model.LastSourceStreamAdmission ?? throw new InvalidOperationException("The real worker did not admit a complete source proof.");
                    var t = admitted.Ticket; var proof = admitted.Proof;
                    var endpoint = model.LastSourceStreamNativeError == 3 ? "unavailable" : model.SourcePlaybackStatus is not null ? "started" : "failed";
                    var track = proof.GetProperty("sourceTrack");
                    var contributors = track.GetProperty("events").EnumerateArray().Select(e => new {
                        event_id = e.GetProperty("eventID").GetString(), media_sha256 = e.GetProperty("mediaSHA256").GetString(),
                        source_ordinal = e.GetProperty("sourceOrdinal").GetUInt64() }).ToArray();
                    var expectedContributors = row.GetProperty("events").EnumerateArray().ToArray();
                    Check(t.Mode == SourceAuditionMode.CompleteTrack && t.SampleRate == rate && t.TotalFrames == total && t.StartFrame == expectedStart &&
                        t.Frames == total - expectedStart && generations.Add(t.Generation) && endpoint is "unavailable" or "started" &&
                        proof.GetProperty("sourceSHA256").GetString() == row.GetProperty("sourceSHA256").GetString() &&
                        proof.GetProperty("importReportSHA256").GetString() == row.GetProperty("reportSHA256").GetString() &&
                        contributors.Length == expectedContributors.Length && contributors.All(c => expectedContributors.Any(e =>
                            e.GetProperty("eventID").GetString() == c.event_id && e.GetProperty("mediaSHA256").GetString() == c.media_sha256)) &&
                        before == StateHash(), "source-stream-" + name + "-" + action + "-admission");
                    if (endpoint == "unavailable" && (!model.LastSourceStreamWorkerJoined || model.LastSourceStreamNativeStarted || model.IsPlaying))
                        throw new InvalidOperationException("No-endpoint cleanup did not join the source worker.");
                    admissions.Add(new { action, generation = t.Generation, revision = t.Revision, mode = t.Mode, sample_rate = t.SampleRate,
                        start_frame = t.StartFrame, total_frames = t.TotalFrames, remaining_frames = t.Frames,
                        proof_sha256 = t.ProofSHA256, proof_json = proof.GetRawText(), source_sha256 = proof.GetProperty("sourceSHA256").GetString(),
                        project_manifest_sha256 = proof.GetProperty("projectManifestSHA256").GetString(),
                        current_project_sha256 = proof.GetProperty("currentProjectSHA256").GetString(),
                        report_sha256 = proof.GetProperty("importReportSHA256").GetString(), contributors,
                        fragment_event_ids = track.GetProperty("fragments").EnumerateArray().Select(f => f.GetProperty("eventID").GetString()).ToArray(),
                        worker_admission_valid = true, endpoint_outcome = endpoint, native_started = model.LastSourceStreamNativeStarted,
                        worker_joined = model.LastSourceStreamWorkerJoined, state_sha256 = StateHash() });
                }
                await Invoke(dialog.PlayButton); Admission("play", 0);
                // Pause only when a real endpoint started; an unavailable device
                // is never promoted into a successful live clock observation.
                if (model.IsPlaying) await Invoke(dialog.PauseButton);
                var tail = total - 1000;
                ((IValueProvider)new TextBoxAutomationPeer(dialog.PositionInput).GetPattern(PatternInterface.Value)).SetValue(((double)tail / rate).ToString("R", CultureInfo.CurrentCulture));
                await Invoke(dialog.SeekButton); Admission("seek", tail);
                await Invoke(dialog.PlayButton); Admission("resume", tail);
                if (name == "overlap")
                {
                    var proof = model.LastSourceStreamAdmission!.Proof.GetProperty("sourceTrack");
                    Check(proof.GetProperty("events").EnumerateArray().Any(e => e.GetProperty("eventID").GetString() == anchor) &&
                        !proof.GetProperty("fragments").EnumerateArray().Any(e => e.GetProperty("eventID").GetString() == anchor), "source-stream-covered-contributor-retained");
                    capture = await Capture(); checks.Add("source-stream-minimum-layout-captured");
                }
                await Invoke(dialog.StopButton); await Invoke(dialog.RefreshButton);
                var afterRequests = model.HelperRequestCounts();
                var prepareDelta = afterRequests.GetValueOrDefault("prepareSourceStream") - requestsBefore.GetValueOrDefault("prepareSourceStream");
                var renderDelta = afterRequests.GetValueOrDefault("renderSourceEvent") - requestsBefore.GetValueOrDefault("renderSourceEvent");
                var inspectDelta = afterRequests.GetValueOrDefault("inspectSourceEvent") - requestsBefore.GetValueOrDefault("inspectSourceEvent");
                Check(model.Position == 0 && !model.IsPlaying && model.LastSourceStreamWorkerJoined && prepareDelta == 3 && renderDelta == 0 &&
                    inspectDelta == 1 && model.SourceInspection?.Revision == model.State.Revision && before == StateHash(), "source-stream-" + name + "-cancel-and-helper-responsive");
                records.Add(new { fixture = name, mode = SourceAuditionMode.CompleteTrack, before_state_sha256 = before, after_state_sha256 = StateHash(),
                    revision = model.State.Revision, availability, admissions, prepare_requests = prepareDelta, snapshot_render_requests = renderDelta,
                    inspection_requests = inspectDelta, after_cancel = new { position_seconds = model.Position, is_playing = model.IsPlaying,
                        worker_joined = model.LastSourceStreamWorkerJoined, inspection_revision = model.SourceInspection?.Revision },
                    no_snapshot_render_request = renderDelta == 0, cancel_joined = model.LastSourceStreamWorkerJoined, helper_responsive = true });
                await Invoke(dialog.CloseButton); dialog = null;
            }
            return new { tested = true, fixture_sha256 = Hash(fixtureBytes), cases = records, capture,
                audio_device_playback_measured = false, physical_input_tested = false, native_frame_visual_tested = false,
                input_evidence = "WPF UI Automation providers invoke production Play, source position/Seek, Stop and refresh actions; no physical input" };
        }
        finally
        {
            if (dialog is { IsVisible: true, Working: false }) dialog.Close();
        }
    }
}
