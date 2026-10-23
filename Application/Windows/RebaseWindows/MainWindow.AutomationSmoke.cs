using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using System.Windows;
using System.Windows.Automation.Peers;
using System.Windows.Automation.Provider;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace Rebase.Windows;

public partial class MainWindow
{
    private async Task<object> RunAutomationSmoke(string artifactRoot, string work, List<string> checks, Action<string> setStage, CancellationToken cancellationToken)
    {
        var phases = new List<object>(); var captures = new List<object>();
        AutomationEditorWindow? editor = null;
        string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        string ProjectHash() => Hash(JsonSerializer.SerializeToUtf8Bytes(model.Project, ProtocolJson.Options));
        string StateHash() => Hash(JsonSerializer.SerializeToUtf8Bytes(model.State, ProtocolJson.Options));
        string LaneHash(string parameter) => Hash(JsonSerializer.SerializeToUtf8Bytes(AutomationLaneView.Read(model.SelectedTrack!, parameter), ProtocolJson.Options));
        void Check(bool good, string name) { setStage(name); if (!good) throw new InvalidOperationException(name + ": " + (editor?.Message ?? model.Status)); checks.Add(name); }
        void Phase(string name) => phases.Add(new { name, project_sha256 = ProjectHash(), revision = model.State.Revision,
            track_id = model.State.Selection.TrackID, clip_id = model.State.Selection.ClipID, volume_sha256 = LaneHash("gainDB"), pan_sha256 = LaneHash("pan") });
        async Task Idle()
        {
            var until = DateTime.UtcNow.AddSeconds(15);
            do
            {
                cancellationToken.ThrowIfCancellationRequested();
                await Dispatcher.InvokeAsync(() => { UpdateLayout(); editor?.UpdateLayout(); }, DispatcherPriority.ApplicationIdle);
                if (!model.Busy && editor?.Working != true) return;
                await Task.Delay(20, cancellationToken);
            } while (DateTime.UtcNow < until);
            throw new TimeoutException("Automation edit did not complete: " + model.Status);
        }
        async Task Invoke(Button button)
        {
            if (!button.IsVisible || !button.IsEnabled) throw new InvalidOperationException("Automation action is not available: " + button.Content);
            ((IInvokeProvider)new ButtonAutomationPeer(button).GetPattern(PatternInterface.Invoke)).Invoke();
            await Idle();
        }
        void Text(TextBox box, string value) => ((IValueProvider)new TextBoxAutomationPeer(box).GetPattern(PatternInterface.Value)).SetValue(value);
        void Enter(TextBox box) => box.RaiseEvent(new KeyEventArgs(Keyboard.PrimaryDevice, PresentationSource.FromVisual(editor!), Environment.TickCount, Key.Enter) { RoutedEvent = Keyboard.PreviewKeyDownEvent });
        async Task SelectParameter(int index)
        {
            var combo = editor!.ParameterBox;
            var peer = new ComboBoxAutomationPeer(combo);
            ((IExpandCollapseProvider)peer.GetPattern(PatternInterface.ExpandCollapse)).Expand();
            await Dispatcher.InvokeAsync(editor.UpdateLayout, DispatcherPriority.ApplicationIdle);
            var item = peer.GetChildren()?.Select(child => child.GetPattern(PatternInterface.SelectionItem)).OfType<ISelectionItemProvider>().ElementAt(index)
                ?? throw new InvalidOperationException("The automation parameter has no UI item.");
            item.Select();
            ((IExpandCollapseProvider)peer.GetPattern(PatternInterface.ExpandCollapse)).Collapse(); await Idle();
        }
        async Task SelectPoint(int index)
        {
            var list = editor!.PointList; list.ScrollIntoView(list.Items[index]); list.UpdateLayout();
            var peer = new ListBoxAutomationPeer(list);
            var item = peer.GetChildren()?.Select(child => child.GetPattern(PatternInterface.SelectionItem)).OfType<ISelectionItemProvider>().ElementAt(index)
                ?? throw new InvalidOperationException("The automation point has no UI item.");
            item.Select(); await Idle();
        }
        async Task<string> Render(string name)
        {
            var path = Path.Combine(work, name + ".wav"); await model.RenderTo(path);
            if (!File.Exists(path) || !model.Status.StartsWith("Exported WAV:", StringComparison.Ordinal)) throw new InvalidOperationException("Automation render failed: " + model.Status);
            return Hash(await File.ReadAllBytesAsync(path, cancellationToken));
        }
        async Task Capture(string name)
        {
            await Idle(); var surface = (FrameworkElement)editor!.Content; var dpi = VisualTreeHelper.GetDpi(surface);
            var width = checked((int)Math.Ceiling(surface.ActualWidth * dpi.DpiScaleX)); var height = checked((int)Math.Ceiling(surface.ActualHeight * dpi.DpiScaleY));
            var bitmap = new RenderTargetBitmap(width, height, dpi.PixelsPerInchX, dpi.PixelsPerInchY, PixelFormats.Pbgra32); bitmap.Render(surface);
            var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
            var path = Path.Combine(artifactRoot, name); using (var stream = File.Create(path)) encoder.Save(stream);
            var controls = new List<object>();
            foreach (var (controlName, element) in new (string, FrameworkElement)[] {
                ("parameter",editor.ParameterBox),("read",editor.ReadButton),("curve",editor.Curve),("points",editor.PointList),
                ("time",editor.TimeBox),("value",editor.ValueBox),("interpolation",editor.InterpolationBox),("add",editor.AddButton),
                ("update",editor.UpdateButton),("delete",editor.DeleteButton),("reset",editor.ResetButton),("undo",editor.UndoButton),("redo",editor.RedoButton),("close",editor.CloseButton) })
            {
                var point = element.TransformToAncestor(surface).Transform(new Point());
                if (!element.IsVisible || element.ActualWidth <= 0 || element.ActualHeight <= 0 || point.X < -0.5 || point.Y < -0.5 || point.X + element.ActualWidth > surface.ActualWidth + 0.5 || point.Y + element.ActualHeight > surface.ActualHeight + 0.5)
                    throw new InvalidOperationException("Automation control outside minimum client capture: " + controlName);
                controls.Add(new { name = controlName, x = point.X, y = point.Y, width = element.ActualWidth, height = element.ActualHeight });
            }
            if (editor.Curve.Plot.Width < 300 || editor.Curve.Plot.Height < 80 || editor.PointList.ActualHeight < 140)
                throw new InvalidOperationException("Automation curve or list has no usable minimum-size viewport.");
            captures.Add(new { file = name, sha256 = Hash(await File.ReadAllBytesAsync(path, cancellationToken)),
                bounds = new { outer_width_dip = editor.ActualWidth, outer_height_dip = editor.ActualHeight, width_dip = surface.ActualWidth, height_dip = surface.ActualHeight,
                    dpi_scale_x = dpi.DpiScaleX, dpi_scale_y = dpi.DpiScaleY, pixel_width = width, pixel_height = height }, controls,
                parameter = editor.Parameter, read_enabled = editor.Lane?.IsReadEnabled ?? true,
                point_count = editor.Lane?.Points.Count ?? 0, curve_duration = editor.Curve.Duration,
                curve_plot = new { x = editor.Curve.Plot.X, y = editor.Curve.Plot.Y, width = editor.Curve.Plot.Width, height = editor.Curve.Plot.Height },
                curve_vertices = editor.Curve.Vertices.Select(point => new { x = point.X, y = point.Y }).ToArray(),
                points = editor.Lane?.Points.Select(point => new { id = point.Id, time = point.Time, value = point.Value, interpolation = point.Interpolation }).ToArray(), message = editor.Message, frame_excluded = true });
        }
        try
        {
            setStage("automation-open");
            var track = model.Project!.Tracks.Single(track => AutomationLaneView.ReadVolume(track)?.Points.Count == 5);
            await model.Command("selectTrack", trackID: track.Id); await Idle();
            var trackID = model.State.Selection.TrackID; var clipID = model.State.Selection.ClipID;
            Phase("original"); var originalProject = ProjectHash(); var originalState = StateHash();
            var originalLane = AutomationLaneView.ReadVolume(model.SelectedTrack!)!;
            AutomationMenu.RaiseEvent(new RoutedEventArgs(MenuItem.ClickEvent));
            await Idle(); editor = activeAutomationEditor ?? throw new InvalidOperationException("Automation editor did not open.");
            await Idle();
            Check(editor.IsVisible && !IsEnabled && StateHash() == originalState, "automation-editor-open-preserves-state");
            Check(editor.Lane?.Points.Count == 5 && editor.PointList.Items.Count == 5 && editor.Curve.Vertices.Count == 7, "automation-volume-five-points-projected");
            Phase("opening");
            editor.Width = editor.MinWidth; editor.Height = editor.MinHeight; await Idle();
            var originalWav = await Render("automation-original");
            await SelectPoint(1); var editedID = editor.SelectedPointID;
            Text(editor.ValueBox, "-4"); editor.InterpolationBox.SelectedIndex = 1;
            await Invoke(editor.UpdateButton);
            Check(editor.Lane!.Id == originalLane.Id && editor.Lane.Points.Count == 5 && editor.Lane.Points[1].Id == editedID && editor.Lane.Points[1].Value == -4 && editor.Lane.Points[1].Interpolation == "step" && ProjectHash() != originalProject, "automation-shared-edit");
            Phase("after_edit"); var editedWav = await Render("automation-edited");
            if (editedWav == originalWav) throw new InvalidOperationException("Editing volume automation did not change the rendered WAV.");
            var editedPoints = JsonSerializer.Serialize(editor.Lane.Points);
            ((IToggleProvider)new CheckBoxAutomationPeer(editor.ReadButton).GetPattern(PatternInterface.Toggle)).Toggle(); await Idle();
            Check(editor.Lane is { IsReadEnabled: false } && JsonSerializer.Serialize(editor.Lane.Points) == editedPoints, "automation-read-off-preserves-points");
            Phase("read_off"); await Capture("native-automation-read-off-visual.png");
            await Invoke(editor.UndoButton); await Invoke(editor.UndoButton);
            Check(ProjectHash() == originalProject, "automation-undo-restores-project"); Phase("after_undo_restored");
            var restoredWav = await Render("automation-restored");
            Check(restoredWav == originalWav, "automation-undo-restores-render");
            await SelectPoint(1); Text(editor.ValueBox, "NaN"); var invalidState = StateHash(); Enter(editor.ValueBox); await Idle();
            Check(StateHash() == invalidState && editor.ValueBox.Text == "NaN" && editor.Message.Contains("finite", StringComparison.Ordinal), "automation-invalid-preserved");
            await Capture("native-automation-invalid-visual.png");
            await Invoke(editor.ResetButton); await SelectPoint(1); Text(editor.ValueBox, "-3"); var draft = editor.DraftRevision;
            await model.Command("setPan", trackID: track.Id, value: track.Pan == 0.5 ? -0.5 : 0.5); await Idle();
            var changedState = StateHash(); await Invoke(editor.UpdateButton);
            Check(model.State.Revision != draft && StateHash() == changedState && editor.ValueBox.Text == "-3" && editor.Message.Contains("changed", StringComparison.OrdinalIgnoreCase), "automation-stale-preserved");
            await Invoke(editor.UndoButton);
            if (ProjectHash() != originalProject) throw new InvalidOperationException("Stale-edit control did not restore the original project.");
            await Capture("native-automation-minimum-visual.png");
            await SelectParameter(1);
            Text(editor.TimeBox, "2.5"); Text(editor.ValueBox, "0.25"); editor.InterpolationBox.SelectedIndex = 1; await Invoke(editor.AddButton);
            var panLane = editor.Lane!; var volumeHash = LaneHash("gainDB");
            Check(editor.Parameter == "pan" && panLane.Points.Count == 1 && panLane.Points[0].Value == 0.25 && panLane.Points[0].Time == 2.5 && panLane.Points[0].Interpolation == "step" && AutomationLaneView.ReadVolume(model.SelectedTrack!)!.Id == originalLane.Id, "automation-pan-edit");
            Phase("pan");
            await SelectParameter(0); var switchedVolume = editor.Lane!.Points.Count == 5 && LaneHash("gainDB") == volumeHash;
            await SelectParameter(1);
            Check(switchedVolume && editor.Lane!.Id == panLane.Id && editor.Lane.Points[0].Id == panLane.Points[0].Id, "automation-parameter-switch");
            var plot = editor.Curve.Plot;
            if (!editor.Curve.InsertAt(new Point(plot.X + plot.Width * 0.375, plot.Y + plot.Height * 0.25))) throw new InvalidOperationException("Curve insertion rejected a point inside its measured plot.");
            await Idle();
            Check(editor.Lane!.Points.Count == 2 && editor.Lane.Points.Any(point => Math.Abs(point.Time - editor.Curve.Duration * 0.375) < 1e-9 && Math.Abs(point.Value - 0.5) < 1e-9) && LaneHash("gainDB") == volumeHash, "automation-curve-point-added");
            Phase("curve"); var beforeDelete = ProjectHash(); var insertedID = editor.SelectedPointID;
            await Invoke(editor.DeleteButton); var deleted = editor.Lane!.Points.Count == 1;
            await Invoke(editor.UndoButton); var restored = ProjectHash() == beforeDelete && editor.Lane!.Points.Any(point => point.Id == insertedID);
            await Invoke(editor.RedoButton); var redone = editor.Lane!.Points.Count == 1;
            await Invoke(editor.UndoButton);
            Check(deleted && restored && redone && ProjectHash() == beforeDelete, "automation-delete-undo-redo");
            var beforeClose = StateHash(); await Invoke(editor.CloseButton); await Idle();
            Check(activeAutomationEditor is null && IsEnabled && StateHash() == beforeClose && AutomationLaneView.Read(model.SelectedTrack!, "pan")!.Points.Count == 2, "automation-close-preserves-edits"); Phase("after_close");
            Check(model.State.Selection.TrackID == trackID && model.State.Selection.ClipID == clipID, "automation-selection-preserved");
            checks.Add("automation-minimum-layout-captured");
            return new { tested = true, editor_open_preserves_state = true, volume_five_points_projected = true, shared_edit = true,
                invalid_preserved = true, stale_preserved = true, read_off_preserves_points = true, undo_restores_project = true, undo_restores_render = true,
                pan_edit = true, parameter_switch = true, curve_point_added = true, delete_undo_redo = true, close_preserves_edits = true, selection_preserved = true,
                original_render_sha256 = originalWav, edited_render_sha256 = editedWav, restored_render_sha256 = restoredWav, phases, captures,
                playback_invalidation_tested = false, physical_input_tested = false, native_frame_visual_tested = false,
                input_evidence = "WPF UIA, injected routed keyboard events, and the production curve input callback with measured plot coordinates; no physical pointer input" };
        }
        catch
        {
            if (editor is { IsVisible: true }) { try { await Capture("native-automation-failure-visual.png"); } catch (Exception) { } }
            throw;
        }
        finally { if (editor is { IsVisible: true, Working: false }) editor.Close(); }
    }
}
