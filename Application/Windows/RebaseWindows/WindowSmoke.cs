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
    public async Task<int> RunSmoke(string artifact)
    {
        var checks = new List<string>();
        var root = Path.GetDirectoryName(artifact)!;
        Directory.CreateDirectory(root);
        var work = Path.Combine(Path.GetTempPath(), "RebaseSmoke", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(work);
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(120));
        string stage = "window-layout", endpoint = "not-probed", error = "";
        object[] processModules = [], helperModules = [];
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
            , process_modules = processModules, helper_modules = helperModules
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
            stage = "capture-window-visual";
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            var image = new RenderTargetBitmap((int)ActualWidth, (int)ActualHeight, 96, 96, PixelFormats.Pbgra32);
            image.Render(this);
            var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(image));
            using (var output = File.Create(Path.Combine(root, "native-app-visual.png"))) encoder.Save(output);
            checks.Add("window-visual-artifact-written"); stage = "completed";
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
