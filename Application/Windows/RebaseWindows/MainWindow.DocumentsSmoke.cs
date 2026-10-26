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
    private async Task<object> RunDocumentsSmoke(string artifactRoot, string work, List<string> checks,
        Action<string> setStage, CancellationToken cancellation)
    {
        string Hash(byte[] bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));
        string StateHash() => Hash(JsonSerializer.SerializeToUtf8Bytes(model.State, ProtocolJson.Options));
        string ProjectHash() => Hash(JsonSerializer.SerializeToUtf8Bytes(model.Project, ProtocolJson.Options));
        var phases = new List<object>();
        var initialSnap = SnapBox.SelectedIndex;
        var initialZoom = Zoom.Value;
        var initialHorizontalOffset = TimelineScroll.HorizontalOffset;
        var initialVerticalOffset = TimelineScroll.VerticalOffset;
        var exampleRoot = Path.Combine(AppContext.BaseDirectory, "Examples", "Rebase Preview.rebaseproj");
        var inputs = new[] { Path.Combine(exampleRoot, "Media", "rhythm.wav"), Path.Combine(exampleRoot, "Media", "pad.wav") };
        var inputHashes = inputs.Select(path => Hash(File.ReadAllBytes(path))).ToArray();
        var initialRequests = model.HelperRequestCounts();
        Dictionary<string, ulong> Requests() => new[] { "newProject", "importAudio", "saveAs", "undo", "redo", "open" }
            .ToDictionary(command => command, command => model.HelperRequestCounts().GetValueOrDefault(command) - initialRequests.GetValueOrDefault(command));
        var saved = Path.Combine(work, "Imported Audio.rebaseproj");
        var invalid = Path.Combine(work, "invalid-import-control.wav");
        await File.WriteAllTextAsync(invalid, "Authored invalid audio control", cancellation);
        object? capture = null;
        var copied = new List<object>();
        void Check(bool value, string label)
        {
            setStage(label);
            if (!value) throw new InvalidOperationException(label + ": " + model.Status);
            checks.Add(label);
        }
        void Record(string phase) => phases.Add(new { phase, state_sha256 = StateHash(), project_sha256 = ProjectHash(),
            revision = model.State.Revision, dirty = model.State.Dirty, needs_save_as = model.State.NeedsSaveAs,
            can_undo = model.State.CanUndo, can_redo = model.State.CanRedo, track_count = model.Project?.Tracks.Length ?? 0,
            track_id = model.State.Selection.TrackID, clip_id = model.State.Selection.ClipID, position_seconds = model.Position,
            requests = Requests() });
        async Task Idle(Func<bool>? completed = null)
        {
            using var limit = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
            limit.CancelAfter(TimeSpan.FromSeconds(120));
            do
            {
                await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
                if (!model.Busy && !documentOperation && IsEnabled && (completed?.Invoke() ?? true)) return;
                await Task.Delay(20, limit.Token);
            } while (true);
        }
        async Task Menu(MenuItem item)
        {
            await Idle();
            FileMenu.IsSubmenuOpen = true;
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            if (!item.IsVisible || !item.IsEnabled) throw new InvalidOperationException("A document menu action is unavailable.");
            ((IInvokeProvider)new MenuItemAutomationPeer(item).GetPattern(PatternInterface.Invoke)).Invoke();
            await Idle(); FileMenu.IsSubmenuOpen = false;
        }
        async Task Button(Button button)
        {
            if (!button.IsVisible || !button.IsEnabled) throw new InvalidOperationException("A document history action is unavailable.");
            ((IInvokeProvider)new ButtonAutomationPeer(button).GetPattern(PatternInterface.Invoke)).Invoke(); await Idle();
        }
        try
        {
            SnapBox.SelectedIndex = 0;
            Zoom.Value = 24;
            TimelineScroll.ScrollToHorizontalOffset(0);
            TimelineScroll.ScrollToVerticalOffset(0);
            smokeNewProjectDecision = () => MessageBoxResult.No;
            await Menu(NewProjectMenu);
            Check(model.Project is { Name: "Untitled", Tracks.Length: 0 } && model.State.NeedsSaveAs && model.State.Path is null &&
                !model.State.Dirty && !model.State.CanUndo && !model.State.CanRedo && model.State.Selection.TrackID is null && model.State.Selection.ClipID is null,
                "documents-new-empty-scratch");
            Record("new");
            smokeAudioPaths = () => null;
            var cancelled = StateHash(); var importCount = model.HelperRequestCounts().GetValueOrDefault("importAudio");
            await Menu(ImportAudioMenu);
            Check(StateHash() == cancelled && model.HelperRequestCounts().GetValueOrDefault("importAudio") == importCount,
                "documents-picker-cancel-preserves-state"); Record("picker_cancelled");
            smokeAudioPaths = () => inputs;
            await Menu(ImportAudioMenu);
            Check(model.Project!.Tracks.Length == 2 && model.Project.Tracks.All(track => track.Clips.Length == 1) &&
                model.State.Dirty && model.State.CanUndo && !model.State.CanRedo && model.State.NeedsSaveAs &&
                model.SelectedTrack?.Id == model.Project.Tracks[^1].Id && model.SelectedClip?.Id == model.Project.Tracks[^1].Clips[0].Id &&
                model.Project.Tracks.All(track => track.Clips[0].Position == 0 && track.Clips[0].Duration == 20),
                "documents-batch-import-selects-last-track");
            var importedProject = ProjectHash(); Record("imported");
            await Idle(() => Timeline.PopulatedWaveformCount == 2);
            Check(Timeline.TrackHeaders.Count == 2 && Timeline.PopulatedWaveformCount == 2, "documents-real-waveforms");
            await Button(UndoButton);
            Check(model.Project!.Tracks.Length == 0 && !model.State.CanUndo && model.State.CanRedo, "documents-batch-single-undo"); Record("undone");
            await Button(RedoButton);
            Check(ProjectHash() == importedProject && model.State.CanUndo && !model.State.CanRedo, "documents-redo-restores-identities"); Record("redone");
            var failedBefore = StateHash();
            importCount = model.HelperRequestCounts().GetValueOrDefault("importAudio");
            smokeAudioPaths = () => [inputs[0], invalid];
            await Menu(ImportAudioMenu);
            Check(StateHash() == failedBefore && model.HelperRequestCounts().GetValueOrDefault("importAudio") == importCount + 1,
                "documents-batch-failure-preserves-state"); Record("batch_rejected");
            smokeNewProjectDecision = () => MessageBoxResult.Cancel;
            var newCount = model.HelperRequestCounts().GetValueOrDefault("newProject");
            await Menu(NewProjectMenu);
            Check(StateHash() == failedBefore && model.HelperRequestCounts().GetValueOrDefault("newProject") == newCount,
                "documents-dirty-new-cancel-preserves-state"); Record("dirty_new_cancelled");
            smokeNewProjectDecision = () => MessageBoxResult.Yes;
            smokeDocumentSaveDestination = () => null;
            await Menu(NewProjectMenu);
            Check(StateHash() == failedBefore && model.HelperRequestCounts().GetValueOrDefault("newProject") == newCount,
                "documents-save-destination-cancel-preserves-state"); Record("save_destination_cancelled");
            smokeDocumentSaveDestination = () => saved;
            await Menu(SaveAsMenu);
            Check(!model.State.Dirty && !model.State.NeedsSaveAs && model.State.Path == saved &&
                File.Exists(Path.Combine(saved, "Project.json")), "documents-save-as-publishes-project"); Record("saved");
            for (var index = 0; index < inputs.Length; index++)
            {
                var clip = model.Project!.Tracks[index].Clips[0];
                var path = Path.GetFullPath(Path.Combine(saved, clip.MediaPath));
                if (!path.StartsWith(Path.GetFullPath(saved) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("Imported media escaped the saved package.");
                var bytes = await File.ReadAllBytesAsync(path, cancellation);
                copied.Add(new { index, media_path = clip.MediaPath, bytes = bytes.Length, sha256 = Hash(bytes),
                    source_sha256 = inputHashes[index], track_id = model.Project.Tracks[index].Id, clip_id = clip.Id,
                    position_seconds = clip.Position, duration_seconds = clip.Duration, source_offset_seconds = clip.SourceOffset,
                    track_clip_count = model.Project.Tracks[index].Clips.Length });
                if (Hash(bytes) != inputHashes[index]) throw new InvalidDataException("Imported media bytes changed.");
            }
            Check(copied.Count == 2, "documents-saved-media-bytes-preserved");
            var savedProject = ProjectHash();
            await Menu(NewProjectMenu);
            Check(model.Project!.Tracks.Length == 0 && model.State.NeedsSaveAs, "documents-clean-new-replaces-project"); Record("clean_new");
            await model.Open(Path.Combine(saved, "Project.json"), false, false); await Idle();
            Check(ProjectHash() == savedProject && !model.State.Dirty && !model.State.NeedsSaveAs,
                "documents-reopen-preserves-project"); Record("reopened");
            await Idle(() => Timeline.PopulatedWaveformCount == 2);
            Check(inputs.Select(path => Hash(File.ReadAllBytes(path))).SequenceEqual(inputHashes), "documents-source-files-unchanged");
            var content = (FrameworkElement)Content; var dpi = VisualTreeHelper.GetDpi(content);
            var width = checked((int)Math.Ceiling(content.ActualWidth * dpi.DpiScaleX));
            var height = checked((int)Math.Ceiling(content.ActualHeight * dpi.DpiScaleY));
            var bitmap = new RenderTargetBitmap(width, height, dpi.PixelsPerInchX, dpi.PixelsPerInchY, PixelFormats.Pbgra32); bitmap.Render(content);
            var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
            const string filename = "native-audio-import-visual.png";
            var imagePath = Path.Combine(artifactRoot, filename); using (var stream = File.Create(imagePath)) encoder.Save(stream);
            var alphaCoverage = MeasureClientAlpha(bitmap, content);
            var imageHash = Hash(await File.ReadAllBytesAsync(imagePath, cancellation));
            await File.WriteAllTextAsync(Path.Combine(artifactRoot, "native-audio-import-visual-alpha.json"),
                JsonSerializer.Serialize(new { screenshot = filename, png_sha256 = imageHash, alpha_coverage = alphaCoverage }), cancellation);
            if (alphaCoverage["root_background_alpha"] != 255 || alphaCoverage["alpha_below_254_pixels"] != 0)
                throw new InvalidOperationException("Audio-import capture failed measured alpha coverage; inspect its retained PNG and alpha diagnostic.");
            object Box(FrameworkElement element, string trackID, string? clipID = null)
            {
                var point = element.TransformToAncestor(content).Transform(new Point());
                if (!element.IsVisible || element.ActualWidth <= 0 || element.ActualHeight <= 0 || point.X < -0.5 || point.Y < -0.5 ||
                    point.X + element.ActualWidth > content.ActualWidth + 0.5 || point.Y + element.ActualHeight > content.ActualHeight + 0.5)
                    throw new InvalidOperationException("An imported event or track is outside the actual client capture.");
                return new { x = point.X, y = point.Y, width = element.ActualWidth, height = element.ActualHeight,
                    track_id = trackID, clip_id = clipID };
            }
            capture = new { file = filename, sha256 = imageHash, alpha_coverage = alphaCoverage,
                bounds = new { outer_width_dip = ActualWidth, outer_height_dip = ActualHeight,
                    width_dip = content.ActualWidth, height_dip = content.ActualHeight, dpi_scale_x = dpi.DpiScaleX, dpi_scale_y = dpi.DpiScaleY,
                    pixel_width = width, pixel_height = height },
                headers = Timeline.TrackHeaders.Select(header => Box(header, (string)header.Tag)).ToArray(),
                clips = Timeline.Children.OfType<Button>().Select(button => Box(button,
                    model.Project!.Tracks.Single(track => track.Clips.Any(clip => clip.Id == (string)button.Tag)).Id, (string)button.Tag)).ToArray(),
                waveform_count = Timeline.PopulatedWaveformCount, pixels_per_second = Zoom.Value,
                horizontal_offset = TimelineScroll.HorizontalOffset, vertical_offset = TimelineScroll.VerticalOffset,
                frame_excluded = true };
            Check(true, "documents-import-window-captured");
            var invalidBytes = await File.ReadAllBytesAsync(invalid, cancellation);
            return new { tested = true, phases,
                helper_sha256 = Hash(await File.ReadAllBytesAsync(Path.Combine(AppContext.BaseDirectory, "rebase-session.exe"), cancellation)),
                example_manifest_sha256 = Hash(await File.ReadAllBytesAsync(Path.Combine(AppContext.BaseDirectory, "Examples", "example.json"), cancellation)),
                invalid_input = new { bytes = invalidBytes.Length, sha256 = Hash(invalidBytes) },
                inputs = inputs.Select((path, index) => new {
                    path = Path.GetRelativePath(AppContext.BaseDirectory, path).Replace('\\', '/'), sha256 = inputHashes[index], bytes = new FileInfo(path).Length }).ToArray(),
                copied_media = copied, capture,
                requests = Requests(),
                physical_input_tested = false, native_file_pickers_tested = false, playback_tested = false,
                input_evidence = "Actual WPF File menu/UIA controls with injected file paths and dirty-decision results; no physical dialogs" };
        }
        finally
        {
            smokeNewProjectDecision = null; smokeAudioPaths = null; smokeDocumentSaveDestination = null;
            FileMenu.IsSubmenuOpen = false; SnapBox.SelectedIndex = initialSnap;
            Zoom.Value = initialZoom;
            TimelineScroll.ScrollToHorizontalOffset(initialHorizontalOffset);
            TimelineScroll.ScrollToVerticalOffset(initialVerticalOffset);
        }
    }
}
