using System.Diagnostics;
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
    public async Task<int> RunSmoke(string artifact, string? sourceProject = null, string? sourceMedia = null)
    {
        var checks = new List<string>();
        var root = Path.GetDirectoryName(artifact)!;
        Directory.CreateDirectory(root);
        var work = Path.Combine(Path.GetTempPath(), "RebaseSmoke", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(work);
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(sourceProject is null ? 120 : 180));
        string stage = "window-layout", endpoint = "not-probed", error = "";
        object[] processModules = [], helperModules = [];
        RenderSnapshot? sourceReceipt = null;
        int exit = 1;
        try
        {
            await Scenario().WaitAsync(deadline.Token);
            processModules = Process.GetCurrentProcess().Modules.Cast<ProcessModule>()
                .Select(module => (object)new { name = module.ModuleName, path = module.FileName }).ToArray();
            helperModules = model.HelperModuleReceipt();
            exit = 0;
        }
        catch (Exception failure) { error = failure.Message; }
        finally
        {
            deadline.Cancel();
            timer.Stop(); closeFinished = true;
            try { await model.DisposeAsync(); } catch (Exception failure) { exit = 1; error += " Shutdown: " + failure.Message; }
            try { Directory.Delete(work, recursive: true); } catch (IOException) { } catch (UnauthorizedAccessException) { }
        }
        var result = new
        {
            schema = 1, suite = "windows-wpf-shared-session-smoke", outcome = exit == 0 ? "passed" : "failed",
            stage, checks, error, endpoint, playback_tested = false, audible_output_measured = false,
            ui_evidence = "WPF visual-tree render of the opened window; not a desktop screen capture",
            tested_dialogs = false, screenshot = "native-app-visual.png"
            , process_modules = processModules, helper_modules = helperModules,
            source_journey_tested = sourceProject is not null && checks.Contains("source-window-visual-artifact"),
            source_screenshot = sourceProject is null ? null : "native-source-visual.png",
            source_output_sha256 = sourceReceipt?.Sha256, source_sha256 = sourceReceipt?.SourceSHA256, media_sha256 = sourceReceipt?.MediaSHA256
            , dark_caption_hresult = darkCaptionResult, native_frame_visual_tested = false
        };
        try { await File.WriteAllTextAsync(artifact, JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true })); }
        catch (IOException) { return 2; }
        return exit;

        async Task Scenario()
        {
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            Assert(IsVisible && ActualWidth >= 1020 && ActualHeight >= 700, "visible-window-layout");
            stage = "open-example-button"; await Invoke(ExampleButton);
            await Until(() => model.Project?.Tracks.Length == 4 && !model.Busy, stage);
            Assert(model.State.NeedsSaveAs && model.State.Path is null, "bundled-example-is-copy");
            var first = model.Project!.Tracks.SelectMany(t => t.Clips).First();
            stage = "select-clip-button";
            await Invoke(Timeline.Children.OfType<Button>().First());
            await Until(() => model.State.Selection.ClipID == first.Id && !model.Busy, stage);
            Assert(model.SelectedClip is not null, "clip-selection");
            stage = "move-button"; MoveBox.Text = (first.Position + 0.25).ToString(System.Globalization.CultureInfo.CurrentCulture); await Invoke(MoveButton);
            await Until(() => model.SelectedClip?.Position == first.Position + 0.25 && !model.Busy, stage);
            Assert(model.State.Dirty, "move-changes-document");
            stage = "undo-button"; await Invoke(UndoButton);
            await Until(() => model.SelectedClip?.Position == first.Position && !model.Busy, stage);
            Assert(model.State.CanRedo, "shared-undo");
            stage = "redo-button"; await Invoke(RedoButton);
            await Until(() => model.SelectedClip?.Position == first.Position + 0.25 && !model.Busy, stage);
            Assert(model.State.CanUndo, "shared-redo");
            stage = "shared-save-as";
            var saved = Path.Combine(work, "Smoke.rebaseproj");
            await model.Save(saved);
            Assert(!model.State.Dirty && !model.State.NeedsSaveAs && File.Exists(Path.Combine(saved, "Project.json")), "save-as-persists-project");
            stage = "shared-reopen";
            await model.Open(Path.Combine(saved, "Project.json"), false, false);
            Assert(model.Project!.Tracks.SelectMany(t => t.Clips).First(c => c.Id == first.Id).Position == first.Position + 0.25, "reopen-retains-edit");
            stage = "shared-render";
            var wav = Path.Combine(work, "snapshot.wav");
            await model.RenderTo(wav);
            Assert(File.Exists(wav) && new FileInfo(wav).Length > 44 && model.Status.StartsWith("Exported WAV:", StringComparison.Ordinal), "render-hash-and-format-verified");
            stage = "native-endpoint-probe";
            await using (var probe = new NativeAudio())
            {
                try { var format = await probe.Format(); endpoint = $"observed-{format.SampleRate}Hz-{format.Channels}channels"; }
                catch (NativeAudioException unavailable) when (unavailable.Code == 3) { endpoint = "unavailable-no-endpoint"; }
            }
            checks.Add("native-dll-endpoint-probe-completed");
            if (sourceProject is not null && sourceMedia is not null)
            {
                stage = "open-source-package";
                await model.Open(sourceProject, true, false);
                Assert(model.SourceEvents.Length > 0 && model.State.NeedsSaveAs && model.State.Path is null, "source-package-copy");
                stage = "source-event-ui-selection";
                var selector = new ComboBoxAutomationPeer(SourceEventsBox);
                var expand = (IExpandCollapseProvider)selector.GetPattern(PatternInterface.ExpandCollapse);
                expand.Expand(); await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
                var item = selector.GetChildren()?.Select(peer => peer.GetPattern(PatternInterface.SelectionItem)).OfType<ISelectionItemProvider>().FirstOrDefault()
                    ?? throw new InvalidOperationException("The source-event selector exposed no selectable UI item.");
                item.Select(); expand.Collapse();
                await Until(() => !model.Busy && model.SelectedSourceEvent is not null, stage);
                Assert(SourceEventsBox.SelectedItem is SourceEventView, "source-event-ui-selection");
                stage = "source-media-ui-attachment";
                smokeAttachPath = sourceMedia;
                await Invoke(AttachSourceButton);
                await Until(() => !model.Busy && model.SelectedSourceEvent?.MediaSHA256 is not null, stage);
                Assert(model.State.Dirty, "source-media-ui-attachment");
                stage = "source-attachment-undo"; await Invoke(UndoButton);
                await Until(() => !model.Busy && model.SelectedSourceEvent?.MediaSHA256 is null, stage);
                Assert(model.State.CanRedo, "source-attachment-undo");
                stage = "source-attachment-redo"; await Invoke(RedoButton);
                await Until(() => !model.Busy && model.SelectedSourceEvent?.MediaSHA256 is not null, stage);
                Assert(model.State.CanUndo, "source-attachment-redo");
                stage = "source-export-ui-verified";
                smokeSourceExportPath = Path.Combine(work, "source-export.wav");
                await Invoke(ExportSourceButton);
                await Until(() => !model.Busy && model.LastSourceExport is not null, stage);
                sourceReceipt = model.LastSourceExport!;
                Assert(File.Exists(smokeSourceExportPath) && model.Status.StartsWith("Exported source WAV:", StringComparison.Ordinal), "source-export-ui-verified");
                Assert(sourceReceipt.Kind == "sourceEvent" && sourceReceipt.EventID == model.SelectedSourceEvent?.Id &&
                    sourceReceipt.SourceSHA256 == model.SelectedSourceEvent?.SourceSHA256 && sourceReceipt.MediaSHA256 == model.SelectedSourceEvent?.MediaSHA256, "source-provenance-matches");
                await Capture("native-source-visual.png"); checks.Add("source-window-visual-artifact");
                smokeAttachPath = smokeSourceExportPath = null;
                await model.Open(Path.Combine(AppContext.BaseDirectory, "Examples", "Rebase Preview.rebaseproj", "Project.json"), true, true);
            }
            stage = "real-waveforms";
            await Until(() => Timeline.PopulatedWaveformCount == model.Project!.Tracks.Sum(track => track.Clips.Length), stage);
            Assert(Timeline.PopulatedWaveformCount > 0, "real-waveforms-visible");
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            Assert(model.Project!.Tracks.Length == 4 && TimelineScroll.ViewportHeight >= Timeline.TracksBottom, "four-track-rows-fit");
            stage = "capture-window-visual";
            await Capture("native-app-visual.png");
            checks.Add("window-visual-artifact-written"); stage = "completed";
        }
        async Task Capture(string filename)
        {
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            var image = new RenderTargetBitmap((int)ActualWidth, (int)ActualHeight, 96, 96, PixelFormats.Pbgra32);
            image.Render(this);
            var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(image));
            using var output = File.Create(Path.Combine(root, filename)); encoder.Save(output);
        }
        void Assert(bool condition, string check) { deadline.Token.ThrowIfCancellationRequested(); if (!condition) throw new InvalidOperationException(check + ": " + model.Status); checks.Add(check); }
        async Task Until(Func<bool> condition, string label)
        {
            var watch = Stopwatch.StartNew();
            while (!condition())
            {
                if (watch.Elapsed > TimeSpan.FromSeconds(20)) throw new TimeoutException(label + ": " + model.Status);
                await Task.Delay(25, deadline.Token);
            }
        }
        static async Task Invoke(Button button)
        {
            var peer = new ButtonAutomationPeer(button);
            ((IInvokeProvider)peer.GetPattern(PatternInterface.Invoke)).Invoke();
            await button.Dispatcher.InvokeAsync(() => { }, DispatcherPriority.ApplicationIdle);
        }
    }
}
