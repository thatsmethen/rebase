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
    private async Task<object> RunSourceAudioSmoke(string artifactRoot, string work, List<string> checks,
        Action<string> setStage, CancellationToken cancellationToken)
    {
        var fixtureRoot = Environment.GetEnvironmentVariable("REBASE_SMOKE_SOURCE_MODES_FIXTURE")
            ?? throw new InvalidOperationException("The authored source-modes fixture was not supplied.");
        using var expected = JsonDocument.Parse(await File.ReadAllBytesAsync(Path.Combine(fixtureRoot, "expected.json"), cancellationToken));
        var cases = expected.RootElement.GetProperty("cases").EnumerateArray().ToArray();
        var exports = new List<object>(); var captures = new List<object>(); var phases = new List<object>();
        SourceAudioWindow? dialog = null;
        string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        string StateHash() => Hash(JsonSerializer.SerializeToUtf8Bytes(model.State, ProtocolJson.Options));
        void Check(bool good, string name)
        {
            setStage(name);
            if (!good) throw new InvalidOperationException(name + ": " + (dialog?.Message ?? model.Status));
            checks.Add(name);
        }
        async Task Idle()
        {
            var until = DateTime.UtcNow.AddSeconds(25);
            do
            {
                cancellationToken.ThrowIfCancellationRequested();
                await Dispatcher.InvokeAsync(() => { UpdateLayout(); dialog?.UpdateLayout(); }, DispatcherPriority.ApplicationIdle);
                if (!model.Busy && dialog?.Working != true && (!openingSourceAudio || activeSourceAudio is not null)) return;
                await Task.Delay(20, cancellationToken);
            } while (DateTime.UtcNow < until);
            throw new TimeoutException("Source audio action did not complete: " + model.Status);
        }
        async Task Invoke(Button button)
        {
            if (!button.IsVisible || !button.IsEnabled) throw new InvalidOperationException("Source audio action is unavailable: " + button.Content);
            ((IInvokeProvider)new ButtonAutomationPeer(button).GetPattern(PatternInterface.Invoke)).Invoke(); await Idle();
        }
        async Task Select(string mode)
        {
            var index = Array.FindIndex(SourceAuditionMode.All, item => item.Id == mode);
            var list = dialog!.Modes; list.ScrollIntoView(list.Items[index]); list.UpdateLayout();
            var peer = new ListBoxAutomationPeer(list);
            var item = peer.GetChildren()?.Select(child => child.GetPattern(PatternInterface.SelectionItem)).OfType<ISelectionItemProvider>().ElementAt(index)
                ?? throw new InvalidOperationException("Source mode has no accessible list item.");
            item.Select(); await Idle();
            if (dialog.SelectedMode != mode) throw new InvalidOperationException("The UI selected a different source mode.");
        }
        async Task Capture(string name)
        {
            await Idle(); var surface = (FrameworkElement)dialog!.Content; var dpi = VisualTreeHelper.GetDpi(surface);
            var width = checked((int)Math.Ceiling(surface.ActualWidth * dpi.DpiScaleX));
            var height = checked((int)Math.Ceiling(surface.ActualHeight * dpi.DpiScaleY));
            var bitmap = new RenderTargetBitmap(width, height, dpi.PixelsPerInchX, dpi.PixelsPerInchY, PixelFormats.Pbgra32); bitmap.Render(surface);
            var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
            var path = Path.Combine(artifactRoot, name); using (var stream = File.Create(path)) encoder.Save(stream);
            var controls = new List<object>();
            foreach (var (controlName, element) in new (string, FrameworkElement)[] {
                ("modes",dialog.Modes),("refresh",dialog.RefreshButton),("export",dialog.ExportButton),
                ("play",dialog.PlayButton),("pause",dialog.PauseButton),("stop",dialog.StopButton),("close",dialog.CloseButton) })
            {
                var point = element.TransformToAncestor(surface).Transform(new Point());
                if (!element.IsVisible || element.ActualWidth <= 0 || element.ActualHeight <= 0 || point.X < -0.5 || point.Y < -0.5 ||
                    point.X + element.ActualWidth > surface.ActualWidth + 0.5 || point.Y + element.ActualHeight > surface.ActualHeight + 0.5)
                    throw new InvalidOperationException("Source audio control outside minimum client capture: " + controlName);
                controls.Add(new { name = controlName, x = point.X, y = point.Y, width = element.ActualWidth, height = element.ActualHeight, enabled = element.IsEnabled });
            }
            if (dialog.Modes.ActualWidth < 220 || dialog.Modes.ActualHeight < 250) throw new InvalidOperationException("The source-mode list has no usable minimum viewport.");
            captures.Add(new { file = name, sha256 = Hash(await File.ReadAllBytesAsync(path, cancellationToken)),
                bounds = new { outer_width_dip = dialog.ActualWidth, outer_height_dip = dialog.ActualHeight, width_dip = surface.ActualWidth, height_dip = surface.ActualHeight,
                    dpi_scale_x = dpi.DpiScaleX, dpi_scale_y = dpi.DpiScaleY, pixel_width = width, pixel_height = height }, controls,
                selected_mode = dialog.SelectedMode, details = dialog.Details, message = dialog.Message, frame_excluded = true });
        }
        try
        {
            foreach (var fixture in cases)
            {
                var name = fixture.GetProperty("name").GetString()!;
                setStage("source-modes-" + name + "-open");
                await model.Open(Path.Combine(fixtureRoot, fixture.GetProperty("root").GetString()!.Replace('/', Path.DirectorySeparatorChar)), true, true);
                await model.Command("selectClip", clipID: fixture.GetProperty("anchorID").GetString()); await Idle();
                var before = StateHash();
                await Invoke(SourceAudioButton); dialog = activeSourceAudio ?? throw new InvalidOperationException("Source audio dialog did not open.");
                await Idle(); dialog.Width = dialog.MinWidth; dialog.Height = dialog.MinHeight; await Idle();
                Check(dialog.IsVisible && !IsEnabled && before == StateHash() && dialog.Modes.Items.Count == 8, "source-modes-" + name + "-open-preserves-state");
                Close(); await Idle();
                Check(IsVisible && activeSourceAudio == dialog && dialog.IsVisible && before == StateHash(), "source-modes-" + name + "-owner-close-guarded");
                var inspection = model.SourceInspection!;
                if (name == "single") Check(inspection.Modes.All(mode => mode.Available), "source-modes-all-eight-available");
                var modes = name == "single" ? SourceAuditionMode.All.Select(mode => mode.Id).ToArray() : [SourceAuditionMode.CompleteTrack];
                foreach (var mode in modes)
                {
                    await Select(mode); var available = inspection.Modes.Single(item => item.Mode == mode);
                    Check(available.Available && dialog.ExportButton.IsEnabled && dialog.PlayButton.IsEnabled &&
                        dialog.Details.Contains(available.SampleRate!.Value.ToString("0", CultureInfo.CurrentCulture), StringComparison.Ordinal) && before == StateHash(),
                        "source-modes-" + name + "-" + mode + "-selection");
                    var path = Path.Combine(work, "source-modes-" + name + "-" + mode + ".wav"); dialog.SmokeExportPath = path;
                    await Invoke(dialog.ExportButton);
                    var info = model.LastSourceExport ?? throw new InvalidOperationException("Source audio export failed: " + model.Status);
                    Check(info.Mode == mode && info.SampleRate == available.SampleRate && info.TotalFrames == available.Frames && info.StartFrame == 0 &&
                        File.Exists(path) && File.Exists(path + ".source-audition.json") && before == StateHash(), "source-modes-" + name + "-" + mode + "-export");
                    using var manifest = JsonDocument.Parse(await File.ReadAllBytesAsync(path + ".source-audition.json", cancellationToken));
                    var proof = manifest.RootElement;
                    var contributors = mode == SourceAuditionMode.CompleteTrack ? proof.GetProperty("sourceTrack").GetProperty("events").GetArrayLength() : 0;
                    var fragments = mode == SourceAuditionMode.CompleteTrack ? proof.GetProperty("sourceTrack").GetProperty("fragments").GetArrayLength() : 0;
                    exports.Add(new { fixture = name, mode, sample_rate = info.SampleRate, frames = info.Frames,
                        source_sha256 = info.SourceSHA256, media_sha256 = info.MediaSHA256, wav_sha256 = info.Sha256,
                        manifest_sha256 = info.ManifestSHA256, contributors, fragments, state_sha256 = before });
                    if (name == "overlap")
                    {
                        var track = proof.GetProperty("sourceTrack"); var anchor = fixture.GetProperty("anchorID").GetString();
                        Check(contributors == 3 && fragments == 3 && track.GetProperty("events").EnumerateArray().Any(row => row.GetProperty("eventID").GetString() == anchor) &&
                            !track.GetProperty("fragments").EnumerateArray().Any(row => row.GetProperty("eventID").GetString() == anchor), "source-modes-covered-contributor-retained");
                    }
                }
                await Capture(name == "single" ? "native-source-modes-converted-visual.png" : "native-source-modes-track-visual.png");
                if (name == "single")
                {
                    var path = dialog.SmokeExportPath!; var wavHash = Hash(await File.ReadAllBytesAsync(path, cancellationToken));
                    var proofHash = Hash(await File.ReadAllBytesAsync(path + ".source-audition.json", cancellationToken));
                    await Invoke(dialog.ExportButton);
                    Check(model.LastSourceExport is null && Hash(await File.ReadAllBytesAsync(path, cancellationToken)) == wavHash &&
                        Hash(await File.ReadAllBytesAsync(path + ".source-audition.json", cancellationToken)) == proofHash && before == StateHash(), "source-modes-existing-export-preserved");
                }
                else
                {
                    var unavailable = inspection.Modes.FirstOrDefault(item => !item.Available)
                        ?? throw new InvalidOperationException("The trimmed authored event did not exercise an unavailable source mode.");
                    await Select(unavailable.Mode);
                    Check(!dialog.ExportButton.IsEnabled && !dialog.PlayButton.IsEnabled && dialog.Message == unavailable.Reason && before == StateHash(), "source-modes-unavailable-reason-and-controls");
                    await Capture("native-source-modes-unavailable-visual.png");
                }
                await Invoke(dialog.RefreshButton);
                Check(model.SourceInspection is not null && before == StateHash(), "source-modes-" + name + "-refresh-read-only");
                await Invoke(dialog.CloseButton); await Idle();
                Check(activeSourceAudio is null && IsEnabled && before == StateHash(), "source-modes-" + name + "-close-preserves-state");
                phases.Add(new { fixture = name, before_sha256 = before, after_sha256 = StateHash(), revision = model.State.Revision }); dialog = null;
            }
            checks.Add("source-modes-minimum-layout-captured");
            return new { tested = true, all_eight_exports_verified = true, complete_track_covered_contributor_verified = true,
                inspection_and_export_read_only = true, owner_close_guarded = true, unavailable_controls_guarded = true,
                existing_export_preserved = true, exports, phases, captures, audio_device_playback_tested = false,
                physical_input_tested = false, native_file_pickers_tested = false, native_frame_visual_tested = false,
                input_evidence = "WPF UI Automation button and list selection providers; save paths injected before the production export action" };
        }
        catch { if (dialog is { IsVisible: true }) { try { await Capture("native-source-modes-failure-visual.png"); } catch (Exception) { } } throw; }
        finally { if (dialog is { IsVisible: true, Working: false }) dialog.Close(); }
    }
}
