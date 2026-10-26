using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Automation.Peers;
using System.Windows.Automation.Provider;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
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
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(sourceProject is null ? 180 : 240));
        string stage = "window-layout", endpoint = "not-probed", error = "";
        object[] processModules = [], helperModules = [];
        object? timelineScrollReceipt = null;
        object? windowBounds = null;
        object? musicalRulerReceipt = null;
        var faderScaleReceipt = new List<object>();
        object? channelAlignment = null;
        object? cprReviewReceipt = null, automationReceipt = null, sourceModesReceipt = null, sourceStreamReceipt = null;
        object? workspaceReceipt = null, workspaceSourceOnly = null;
        object? topRowsLayout = null, topRowsLongNames = null, topRowsResize = null, topRowsFailure = null;
        var topRowsStates = new List<object>();
        var topRowsCaptures = new List<object>();
        string? failureScreenshot = null;
        var workspaceStates = new List<object>();
        var workspaceTargets = new List<object>();
        var workspaceFaders = new List<object>();
        var workspaceCaptureSafety = new List<object>();
        string? workspaceInitialHash = null;
        object? workspaceSplitter = null;
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
        catch (Exception failure)
        {
            error = failure.Message;
            // Preserve the measured failing state before disposing the helper.
            // A failed assertion must not erase the layout that caused it.
            if (IsVisible && Content is FrameworkElement { ActualWidth: > 0, ActualHeight: > 0 })
            {
                try
                {
                    await Capture("native-workspace-failure-visual.png");
                    failureScreenshot = "native-workspace-failure-visual.png";
                    topRowsFailure = new { stage, bands = new[] { (FrameworkElement)MenuBand, ToolbarBand, ProjectStatusBand, EventInfoBand }.Select(element => new { name = element.Name, bounds = Box(BoundsOf(element)) }).ToArray(),
                        event_controls = new[] { (FrameworkElement)SelectionName, SelectionKind, MoveBox, MoveButton, TrimBox, TrimButton, SourceOffsetText }.Select(element => new { name = element.Name, bounds = Box(BoundsOf(element)) }).ToArray() };
                    if (workspaceInitialHash is not null) RefreshWorkspaceReceipt();
                }
                catch (Exception diagnostic) { error += " Layout diagnostic: " + diagnostic.Message; }
            }
        }
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
            , timeline_scroll = timelineScrollReceipt, timeline_scroll_screenshot = "native-timeline-scroll-visual.png"
            , window_bounds = windowBounds
            , musical_ruler = musicalRulerReceipt, fader_scale = faderScaleReceipt, channel_alignment = channelAlignment
            , cpr_review = cprReviewReceipt, automation = automationReceipt, source_modes = sourceModesReceipt, source_stream_window = sourceStreamReceipt, workspace = workspaceReceipt, failure_screenshot = failureScreenshot
            , top_rows = new { layout = topRowsLayout, states = topRowsStates, long_names = topRowsLongNames,
                resize = topRowsResize, captures = topRowsCaptures, failure_layout = topRowsFailure, input_evidence = "UIA and injected routed keyboard events; no physical input" }
        };
        try { await File.WriteAllTextAsync(artifact, JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true })); }
        catch (IOException) { return 2; }
        return exit;

        async Task Scenario()
        {
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            MeasureWindowBounds();
            Assert(IsVisible && ActualWidth >= 1020 && ActualHeight >= 700, "visible-window-layout");
            var snapOrigin = SnapBox.TransformToAncestor(ProjectActions).Transform(new Point());
            Assert(snapOrigin.Y >= 0 && snapOrigin.Y + SnapBox.ActualHeight <= ProjectActions.ActualHeight, "snap-control-fits-toolbar");
            stage = "top-rows-empty-state";
            topRowsLayout = MeasureTopRowsLayout();
            checks.Add("top-rows-compact-layout");
            RecordTimingState("startup-empty", "empty", rejectEdits: true);
            checks.Add("top-rows-empty-state");
            stage = "open-example-button"; await Invoke(ExampleButton);
            await Until(() => model.Project?.Tracks.Length == 4 && !model.Busy, stage);
            Assert(model.State.NeedsSaveAs && model.State.Path is null, "bundled-example-is-copy");
            var first = model.Project!.Tracks.SelectMany(t => t.Clips).First();
            stage = "select-clip-button";
            await Invoke(Timeline.Children.OfType<Button>().First());
            await Until(() => model.State.Selection.ClipID == first.Id && !model.Busy, stage);
            Assert(model.SelectedClip is not null, "clip-selection");
            if (model.SelectedClip!.Position != 0) throw new InvalidOperationException("The ordinary zero control requires a clip starting at zero.");
            RecordTimingState("ordinary-zero", "ordinary", rejectEdits: false);
            var originalTrack = model.SelectedTrack!;
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            Assert(ChannelTrack.Text == originalTrack.Name && InspectorTrack.Text == originalTrack.Name &&
                SelectedChannel.Content is not null &&
                Timeline.TrackHeaders.Single(header => Equals(header.Tag, originalTrack.Id)) is Grid { Background: SolidColorBrush selectedHeader } &&
                selectedHeader.Color == Color.FromRgb(87, 92, 95), "selection-synchronized-across-panes");
            await WorkspaceScenario();
            checks.Add("timeline-dividers-fill-width");

            var targetGain = originalTrack.GainDB >= 24 ? 23 : originalTrack.GainDB + 1;
            stage = "inspector-volume-shared-edit";
            InspectorGainSlider.Focus();
            RangeValue(InspectorGainSlider).SetValue(targetGain);
            await Until(() => model.SelectedTrack?.GainDB == targetGain && !model.Busy, stage);
            Assert(InspectorGainSlider.Value == targetGain && mixerSliders[originalTrack.Id + ":gain"].Value == targetGain && model.State.Dirty, "inspector-volume-shared-edit");
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            Assert(InspectorGainSlider.IsKeyboardFocusWithin, "inspector-focus-restored");
            stage = "inspector-volume-undo"; await Invoke(UndoButton);
            await Until(() => model.SelectedTrack?.GainDB == originalTrack.GainDB && !model.Busy, stage);
            Assert(InspectorGainSlider.Value == originalTrack.GainDB && mixerSliders[originalTrack.Id + ":gain"].Value == originalTrack.GainDB, "inspector-volume-undo");
            stage = "inspector-volume-redo"; await Invoke(RedoButton);
            await Until(() => model.SelectedTrack?.GainDB == targetGain && !model.Busy, stage);
            Assert(InspectorGainSlider.Value == targetGain && mixerSliders[originalTrack.Id + ":gain"].Value == targetGain, "inspector-volume-redo");
            await Invoke(UndoButton); await Until(() => model.SelectedTrack?.GainDB == originalTrack.GainDB && !model.Busy, "restore-inspector-volume");
            stage = "inspector-pan-shared-edit";
            var targetPan = originalTrack.Pan == 0.25 ? -0.25 : 0.25;
            RangeValue(InspectorPanSlider).SetValue(targetPan);
            await Until(() => model.SelectedTrack?.Pan == targetPan && !model.Busy, stage);
            Assert(InspectorPanSlider.Value == targetPan && mixerSliders[originalTrack.Id + ":pan"].Value == targetPan, "inspector-pan-shared-edit");
            await Invoke(UndoButton); await Until(() => model.SelectedTrack?.Pan == originalTrack.Pan && !model.Busy, "restore-inspector-pan");
            stage = "mixer-volume-shared-edit-and-undo";
            mixerSliders[originalTrack.Id + ":gain"].Focus();
            RangeValue(mixerSliders[originalTrack.Id + ":gain"]).SetValue(targetGain);
            await Until(() => model.SelectedTrack?.GainDB == targetGain && !model.Busy, stage);
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            var mixerEditSynchronized = InspectorGainSlider.Value == targetGain && mixerSliders[originalTrack.Id + ":gain"].Value == targetGain &&
                mixerSliders[originalTrack.Id + ":gain"].IsKeyboardFocusWithin;
            await Invoke(UndoButton); await Until(() => model.SelectedTrack?.GainDB == originalTrack.GainDB && !model.Busy, stage);
            Assert(mixerEditSynchronized && InspectorGainSlider.Value == originalTrack.GainDB && mixerSliders[originalTrack.Id + ":gain"].Value == originalTrack.GainDB, "mixer-volume-shared-edit-and-undo");
            stage = "channel-volume-shared-edit-and-undo";
            RangeValue(mixerSliders["channel:" + originalTrack.Id + ":gain"]).SetValue(targetGain);
            await Until(() => model.SelectedTrack?.GainDB == targetGain && !model.Busy, stage);
            Assert(InspectorGainSlider.Value == targetGain && mixerSliders[originalTrack.Id + ":gain"].Value == targetGain &&
                mixerSliders["channel:" + originalTrack.Id + ":gain"].Value == targetGain, "channel-volume-shared-edit");
            await Invoke(UndoButton); await Until(() => model.SelectedTrack?.GainDB == originalTrack.GainDB && !model.Busy, stage);
            Assert(mixerSliders["channel:" + originalTrack.Id + ":gain"].Value == originalTrack.GainDB, "channel-volume-undo");
            stage = "channel-pan-shared-edit";
            RangeValue(mixerSliders["channel:" + originalTrack.Id + ":pan"]).SetValue(targetPan);
            await Until(() => model.SelectedTrack?.Pan == targetPan && !model.Busy, stage);
            Assert(InspectorPanSlider.Value == targetPan && mixerSliders[originalTrack.Id + ":pan"].Value == targetPan, "channel-pan-shared-edit");
            await Invoke(UndoButton); await Until(() => model.SelectedTrack?.Pan == originalTrack.Pan && !model.Busy, stage);
            stage = "channel-mute-shared-edit";
            Toggle(Descendants<CheckBox>(SelectedChannel).Single(control => System.Windows.Automation.AutomationProperties.GetName(control) == "Mute " + originalTrack.Name));
            await Until(() => model.SelectedTrack?.IsMuted == !originalTrack.IsMuted && !model.Busy, stage);
            Assert(InspectorMute.IsChecked == !originalTrack.IsMuted && MixerFlag("Mute " + originalTrack.Name).IsChecked == !originalTrack.IsMuted, "channel-mute-shared-edit");
            await Invoke(UndoButton); await Until(() => model.SelectedTrack?.IsMuted == originalTrack.IsMuted && !model.Busy, stage);
            stage = "fader-scale-matches-value";
            foreach (var db in new double[] { -96, 0, 24 })
            {
                RangeValue(mixerSliders["channel:" + originalTrack.Id + ":gain"]).SetValue(db);
                await Until(() => model.SelectedTrack?.GainDB == db && !model.Busy, stage);
                await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
                foreach (var selectedStrip in new[] { false, true })
                {
                    var slider = mixerSliders[(selectedStrip ? "channel:" : "") + originalTrack.Id + ":gain"];
                    var scale = selectedStrip ? Descendants<FaderScale>(SelectedChannel).Single() : Descendants<FaderScale>(Mixer.Children[0]).Single();
                    var track = (Track)slider.Template.FindName("PART_Track", slider);
                    var thumbY = track.Thumb.TranslatePoint(new Point(track.Thumb.ActualWidth / 2, track.Thumb.ActualHeight / 2), scale).Y;
                    var tickY = scale.TickY(db);
                    if (tickY is null || Math.Abs(tickY.Value - thumbY) > 0.5) throw new InvalidOperationException("Fader tick does not align with its actual thumb.");
                    faderScaleReceipt.Add(new { selected_channel = selectedStrip, value = db, tick_y = tickY.Value, thumb_y = thumbY });
                }
                await Invoke(UndoButton); await Until(() => model.SelectedTrack?.GainDB == originalTrack.GainDB && !model.Busy, stage);
            }
            checks.Add("fader-scale-matches-value");
            stage = "mixer-numeric-volume-commit";
            var gainField = mixerValues[originalTrack.Id + ":gainValue"];
            gainField.Focus(); gainField.Text = targetGain.ToString(System.Globalization.CultureInfo.CurrentCulture); Key(gainField, System.Windows.Input.Key.Enter);
            await Until(() => model.SelectedTrack?.GainDB == targetGain && !model.Busy, stage);
            Assert(InspectorGainSlider.Value == targetGain && mixerSliders["channel:" + originalTrack.Id + ":gain"].Value == targetGain, "mixer-numeric-volume-commit");
            await Invoke(UndoButton); await Until(() => model.SelectedTrack?.GainDB == originalTrack.GainDB && !model.Busy, stage);
            var revisionBeforeInvalid = model.State.Revision;
            gainField = mixerValues[originalTrack.Id + ":gainValue"];
            gainField.Text = "NaN"; Key(gainField, System.Windows.Input.Key.Enter);
            Assert(model.State.Revision == revisionBeforeInvalid && model.SelectedTrack?.GainDB == originalTrack.GainDB &&
                gainField.Text == originalTrack.GainDB.ToString("0.00", System.Globalization.CultureInfo.CurrentCulture), "mixer-numeric-volume-invalid-preserved");
            gainField.Text = "17"; Key(gainField, System.Windows.Input.Key.Escape);
            Assert(model.State.Revision == revisionBeforeInvalid && gainField.Text == originalTrack.GainDB.ToString("0.00", System.Globalization.CultureInfo.CurrentCulture), "mixer-numeric-volume-cancel");
            stage = "inspector-mute-shared-edit"; Toggle(InspectorMute);
            await Until(() => model.SelectedTrack?.IsMuted == !originalTrack.IsMuted && !model.Busy, stage);
            Assert(InspectorMute.IsChecked == !originalTrack.IsMuted && MixerFlag("Mute " + originalTrack.Name).IsChecked == !originalTrack.IsMuted, "inspector-mute-shared-edit");
            await Invoke(UndoButton); await Until(() => model.SelectedTrack?.IsMuted == originalTrack.IsMuted && !model.Busy, "restore-inspector-mute");
            stage = "inspector-solo-shared-edit"; Toggle(InspectorSolo);
            await Until(() => model.SelectedTrack?.IsSolo == !originalTrack.IsSolo && !model.Busy, stage);
            Assert(InspectorSolo.IsChecked == !originalTrack.IsSolo && MixerFlag("Solo " + originalTrack.Name).IsChecked == !originalTrack.IsSolo, "inspector-solo-shared-edit");
            await Invoke(UndoButton); await Until(() => model.SelectedTrack?.IsSolo == originalTrack.IsSolo && !model.Busy, "restore-inspector-solo");
            stage = "mixer-mute-shared-edit"; Toggle(MixerFlag("Mute " + originalTrack.Name));
            await Until(() => model.SelectedTrack?.IsMuted == !originalTrack.IsMuted && !model.Busy, stage);
            Assert(InspectorMute.IsChecked == !originalTrack.IsMuted && MixerFlag("Mute " + originalTrack.Name).IsChecked == !originalTrack.IsMuted, "mixer-mute-shared-edit");
            await Invoke(UndoButton); await Until(() => model.SelectedTrack?.IsMuted == originalTrack.IsMuted && !model.Busy, "restore-mixer-mute");
            stage = "track-solo-shared-edit";
            Toggle(Timeline.TrackHeaders.SelectMany(Descendants<CheckBox>).Single(control => System.Windows.Automation.AutomationProperties.GetName(control) == "Solo " + originalTrack.Name));
            await Until(() => model.SelectedTrack?.IsSolo == !originalTrack.IsSolo && !model.Busy, stage);
            Assert(InspectorSolo.IsChecked == !originalTrack.IsSolo && MixerFlag("Solo " + originalTrack.Name).IsChecked == !originalTrack.IsSolo, "track-solo-shared-edit");
            await Invoke(UndoButton); await Until(() => model.SelectedTrack?.IsSolo == originalTrack.IsSolo && !model.Busy, "restore-track-solo");
            stage = "numeric-event-enter-and-undo";
            MoveBox.Focus(); MoveBox.Text = (first.Position + 0.125).ToString(System.Globalization.CultureInfo.CurrentCulture); Key(MoveBox, System.Windows.Input.Key.Enter);
            await Until(() => model.SelectedClip?.Position == first.Position + 0.125 && !model.Busy, stage);
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            if (!MoveBox.IsKeyboardFocusWithin) throw new InvalidOperationException("Committing the compact event field lost keyboard focus.");
            await Invoke(UndoButton); await Until(() => model.SelectedClip?.Position == first.Position && !model.Busy, stage);
            Assert(model.SelectedClip!.Position == first.Position, "numeric-event-enter-and-undo");
            stage = "numeric-event-cancel-and-invalid";
            var beforeNumeric = model.State.Revision;
            MoveBox.Text = "23"; Key(MoveBox, System.Windows.Input.Key.Escape);
            Assert(model.State.Revision == beforeNumeric && MoveBox.Text == first.Position.ToString("0.######", System.Globalization.CultureInfo.CurrentCulture), "numeric-event-cancel");
            MoveBox.Text = "NaN"; Key(MoveBox, System.Windows.Input.Key.Enter);
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            Assert(model.State.Revision == beforeNumeric && model.SelectedClip?.Position == first.Position, "numeric-event-invalid-preserved");
            Key(MoveBox, System.Windows.Input.Key.Escape);
            stage = "numeric-trim-enter-and-undo";
            TrimBox.Text = (first.Position + first.Duration - 0.125).ToString(System.Globalization.CultureInfo.CurrentCulture); Key(TrimBox, System.Windows.Input.Key.Enter);
            await Until(() => model.SelectedClip?.Duration == first.Duration - 0.125 && !model.Busy, stage);
            await Invoke(UndoButton); await Until(() => model.SelectedClip?.Duration == first.Duration && !model.Busy, stage);
            checks.Add("numeric-trim-enter-and-undo");
            stage = "numeric-tempo-enter-and-undo";
            var tempo = model.Project!.Tempo;
            TempoBox.Text = (tempo + 1).ToString(System.Globalization.CultureInfo.CurrentCulture); Key(TempoBox, System.Windows.Input.Key.Enter);
            await Until(() => model.Project?.Tempo == tempo + 1 && !model.Busy, stage);
            await Invoke(UndoButton); await Until(() => model.Project?.Tempo == tempo && !model.Busy, stage);
            checks.Add("numeric-tempo-enter-and-undo");
            stage = "numeric-seek-and-cancel";
            var beforeSeek = model.State.Revision;
            PositionBox.Text = "1"; Key(PositionBox, System.Windows.Input.Key.Enter);
            await Until(() => model.Position == 1 && !model.Busy, stage);
            PositionBox.Text = "19"; Key(PositionBox, System.Windows.Input.Key.Escape);
            Assert(model.State.Revision == beforeSeek && model.Position == 1 && PositionBox.Text == 1d.ToString("0.000", System.Globalization.CultureInfo.CurrentCulture), "numeric-seek-and-cancel");
            PositionBox.Text = "0"; Key(PositionBox, System.Windows.Input.Key.Enter); await Until(() => model.Position == 0 && !model.Busy, stage);
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
                await CPRImportScenario();
                stage = "open-source-package";
                await model.Open(sourceProject, true, false);
                Assert(model.SourceEvents.Length > 0 && model.State.NeedsSaveAs && model.State.Path is null, "source-package-copy");
                stage = "source-event-ui-selection";
                var selector = new ComboBoxAutomationPeer(SourceEventsBox);
                var expand = (IExpandCollapseProvider)selector.GetPattern(PatternInterface.ExpandCollapse);
                expand.Expand(); await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
                var itemPeer = selector.GetChildren()?.FirstOrDefault(peer => peer.GetPattern(PatternInterface.SelectionItem) is ISelectionItemProvider)
                    ?? throw new InvalidOperationException("The source-event selector exposed no selectable UI item.");
                var accessibleItemName = itemPeer.GetName();
                var item = (ISelectionItemProvider)itemPeer.GetPattern(PatternInterface.SelectionItem);
                item.Select(); expand.Collapse();
                await Until(() => !model.Busy && model.SelectedSourceEvent is not null, stage);
                Assert(SourceEventsBox.SelectedItem is SourceEventView, "source-event-ui-selection");
                await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
                Assert(accessibleItemName == model.SelectedSourceEvent!.DisplayName &&
                    Descendants<TextBlock>(SourceEventsBox).Any(text => text.Text == model.SelectedSourceEvent.DisplayName && text.ActualWidth > 0 && text.ActualHeight > 0) &&
                    SelectionName.Text == model.SelectedSourceEvent.Name && !MoveBox.IsEnabled && !TrimBox.IsEnabled, "source-selection-labels");
                RecordTimingState("retained-source", "source", rejectEdits: true);
                checks.Add("top-rows-source-state");
                var sourceOnlyBefore = SessionHash();
                foreach (var button in new[] { SplitToolbarButton, DeleteToolbarButton, SplitInspectorButton, DeleteInspectorButton, MoveButton })
                {
                    if (button.IsEnabled) throw new InvalidOperationException("An ordinary edit action is enabled for a retained source event.");
                    try { ((IInvokeProvider)new ButtonAutomationPeer(button).GetPattern(PatternInterface.Invoke)).Invoke(); throw new InvalidOperationException("A disabled source-only edit action accepted invocation."); }
                    catch (System.Windows.Automation.ElementNotEnabledException) { }
                }
                Key(MoveBox, System.Windows.Input.Key.Enter); Key(TrimBox, System.Windows.Input.Key.Enter);
                Assert(!SplitMenuItem.IsEnabled && !DeleteMenuItem.IsEnabled && !ClipInspector.IsEnabled && sourceOnlyBefore == SessionHash(), "workspace-source-only-actions");
                var sourceOnlyAfter = SessionHash();
                var eventID = model.SelectedSourceEvent!.Id;
                var sourceHashBefore = model.SelectedSourceEvent.SourceSHA256;
                stage = "source-auto-expand";
                var selectionFixture = await MakeSourceSelectionFixture();
                await model.Open(selectionFixture.Path, true, false);
                if (model.SelectedSourceEvent?.Id != eventID) throw new InvalidOperationException("The derived source fixture changed the initial retained event.");
                ((IExpandCollapseProvider)new ExpanderAutomationPeer(SourceSection).GetPattern(PatternInterface.ExpandCollapse)).Collapse();
                await model.Command("selectTrack", trackID: selectionFixture.ControlTrackID);
                if (model.State.Selection.TrackID != selectionFixture.ControlTrackID || model.State.Selection.ClipID is not null || model.SelectedSourceEvent is not null || SourceSection.IsExpanded)
                    throw new InvalidOperationException("The source auto-expansion control did not leave the retained event selected state.");
                RecordTimingState("empty-track", "empty", rejectEdits: true);
                var otherSelectionID = model.State.Selection.ClipID;
                // Select the retained event only after the shared session has
                // selected the different, empty authored track. Selecting the
                // original track again would correctly retain its source event.
                SourceEventsBox.SelectedItem = model.SourceEvents.Single(source => source.Id == eventID);
                await Until(() => !model.Busy && model.SelectedSourceEvent?.Id == eventID && SourceSection.IsExpanded, stage);
                Assert(SourceSection.IsExpanded && SourcePanel.IsVisible, "workspace-source-auto-expand");
                var sourceHashAfter = model.SelectedSourceEvent!.SourceSHA256;
                if (sourceHashBefore != sourceHashAfter) throw new InvalidOperationException("The derived selection control changed the retained source identity.");
                await model.Open(sourceProject, true, false);
                if (model.Project!.Tracks.Length != 1 || model.SelectedSourceEvent?.Id != eventID || model.SelectedSourceEvent.SourceSHA256 != sourceHashBefore)
                    throw new InvalidOperationException("The canonical source fixture was not restored before attachment and export.");
                workspaceSourceOnly = new { before_sha256 = sourceOnlyBefore, after_sha256 = sourceOnlyAfter, ordinary_actions_disabled = true, source_expanded = true,
                    auto_expand_input = "Programmatic source-list SelectionChanged event through the shared session",
                    auto_expand = new { before_selection_id = eventID, other_track_id = selectionFixture.ControlTrackID, other_selection_id = otherSelectionID,
                        after_selection_id = eventID, source_sha256_before = sourceHashBefore, source_sha256_after = sourceHashAfter,
                        canonical_source_restored = true, derived_fixture = selectionFixture.Receipt } };
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
            await model.Open(Path.Combine(AppContext.BaseDirectory, "Examples", "Rebase Preview.rebaseproj", "Project.json"), true, true);
            sourceModesReceipt = await RunSourceAudioSmoke(root, work, checks, value => stage = value, deadline.Token);
            sourceStreamReceipt = await RunSourceStreamSmoke(root, checks, value => stage = value, deadline.Token);
            await model.Open(Path.Combine(AppContext.BaseDirectory, "Examples", "Rebase Preview.rebaseproj", "Project.json"), true, true);
            automationReceipt = await RunAutomationSmoke(root, work, checks, value => stage = value, deadline.Token);
            await LongNamesScenario();
            await model.Open(Path.Combine(AppContext.BaseDirectory, "Examples", "Rebase Preview.rebaseproj", "Project.json"), true, true);
            stage = "real-waveforms";
            await Until(() => Timeline.PopulatedWaveformCount == model.Project!.Tracks.Sum(track => track.Clips.Length), stage);
            Assert(Timeline.PopulatedWaveformCount > 0, "real-waveforms-visible");
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            Assert(model.Project!.Tracks.Length == 4 && TimelineScroll.ViewportHeight >= Timeline.TracksBottom, "four-track-rows-fit");
            stage = "musical-ruler-shared-96bpm";
            await Until(() => Timeline.MusicalRulerVisible && model.Ruler?.Revision == model.State.Revision && model.Ruler.PixelsPerSecond == Zoom.Value, stage);
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            var barTwo = model.Ruler!.Ticks.Single(tick => tick.Bar && tick.Label == "2");
            var firstBarLabel = Timeline.Children.OfType<TextBlock>().Single(text => text.Tag is RulerTick { Bar: true, Label: "1" });
            var secondBarLabel = Timeline.Children.OfType<TextBlock>().Single(text => text.Tag is RulerTick { Bar: true, Label: "2" });
            Assert(model.Project.Tempo == 96 && barTwo.Seconds == 2.5 && firstBarLabel.ActualWidth > 0 && secondBarLabel.ActualWidth > 0 &&
                Math.Abs(Canvas.GetLeft(secondBarLabel) - Canvas.GetLeft(firstBarLabel) - 2.5 * Zoom.Value) <= 0.5, "musical-ruler-shared-96bpm");
            musicalRulerReceipt = new { revision = model.Ruler.Revision, tempo = model.Project.Tempo, duration = model.Ruler.Duration,
                pixels_per_second = model.Ruler.PixelsPerSecond, bar_two_seconds = barTwo.Seconds,
                first_label_x = Canvas.GetLeft(firstBarLabel), second_label_x = Canvas.GetLeft(secondBarLabel) };
            stage = "musical-ruler-seconds-toggle";
            await SelectComboItem(RulerModeBox, 1);
            Assert(!Timeline.MusicalRulerVisible && Timeline.Children.OfType<TextBlock>().Any(text => text.Tag is null && text.Text == "0") &&
                !Timeline.Children.OfType<TextBlock>().Any(text => text.Tag is RulerTick), "musical-ruler-seconds-toggle");
            await SelectComboItem(RulerModeBox, 0);
            stage = "fixed-track-header-scroll";
            var originalZoom = Zoom.Value;
            Zoom.Value = 100;
            await Until(() => Timeline.MusicalRulerVisible && model.Ruler?.PixelsPerSecond == 100, "zoomed-musical-ruler");
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            var scrollPeer = new ScrollViewerAutomationPeer(TimelineScroll);
            var scroll = (IScrollProvider)scrollPeer.GetPattern(PatternInterface.Scroll);
            scroll.SetScrollPercent(0, System.Windows.Automation.ScrollPatternIdentifiers.NoScroll);
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            var eventButton = Timeline.Children.OfType<Button>().First();
            var headersBefore = Timeline.TrackHeaders.Select(Origin).ToArray();
            var rulerBefore = BoundsOf(Timeline.RulerCornerLabel);
            var rulerHeaderBefore = BoundsOf(Timeline.TrackHeaders[0]);
            ValidateRulerCorner(rulerBefore, rulerHeaderBefore);
            var eventBefore = Origin(eventButton);
            var offsetBefore = TimelineScroll.HorizontalOffset;
            scroll.SetScrollPercent(20, System.Windows.Automation.ScrollPatternIdentifiers.NoScroll);
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            var headersAfter = Timeline.TrackHeaders.Select(Origin).ToArray();
            var rulerAfter = BoundsOf(Timeline.RulerCornerLabel);
            var rulerHeaderAfter = BoundsOf(Timeline.TrackHeaders[0]);
            ValidateRulerCorner(rulerAfter, rulerHeaderAfter);
            Assert(Math.Abs(rulerBefore.X - rulerAfter.X) <= 0.5 && Math.Abs(rulerBefore.Y - rulerAfter.Y) <= 0.5,
                "ruler-corner-stays-visible");
            var eventAfter = Origin(eventButton);
            var offsetAfter = TimelineScroll.HorizontalOffset;
            var offsetDelta = offsetAfter - offsetBefore;
            Assert(offsetDelta >= 50, "timeline-horizontal-scroll-performed");
            Assert(headersBefore.Length == model.Project.Tracks.Length && headersAfter.Length == headersBefore.Length &&
                headersBefore.Zip(headersAfter).All(pair => Math.Abs(pair.First.X - pair.Second.X) <= 0.5 && Math.Abs(pair.First.Y - pair.Second.Y) <= 0.5), "track-headers-stay-anchored");
            Assert(Math.Abs(eventAfter.X - eventBefore.X + offsetDelta) <= 0.5 && Math.Abs(eventAfter.Y - eventBefore.Y) <= 0.5, "timeline-events-scroll");
            timelineScrollReceipt = new
            {
                zoom_pixels_per_second = Zoom.Value, offset_before = offsetBefore, offset_after = offsetAfter,
                headers_before = headersBefore.Select(point => new { x = point.X, y = point.Y }).ToArray(),
                headers_after = headersAfter.Select(point => new { x = point.X, y = point.Y }).ToArray(),
                event_before = new { x = eventBefore.X, y = eventBefore.Y }, event_after = new { x = eventAfter.X, y = eventAfter.Y },
                ruler_before = RulerBox(rulerBefore), ruler_after = RulerBox(rulerAfter),
                ruler_header_before = Box(rulerHeaderBefore), ruler_header_after = Box(rulerHeaderAfter)
            };
            await Capture("native-timeline-scroll-visual.png"); checks.Add("timeline-scroll-visual-artifact");
            scroll.SetScrollPercent(0, System.Windows.Automation.ScrollPatternIdentifiers.NoScroll);
            Zoom.Value = originalZoom;
            await Until(() => Timeline.MusicalRulerVisible && model.Ruler?.PixelsPerSecond == originalZoom, "restored-musical-ruler");
            stage = "channel-strip-bottom-aligned";
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            var selectedNamePlate = Descendants<Button>(SelectedChannel).Single();
            var mixerNamePlate = Descendants<Button>(Mixer.Children[0]).Single();
            var selectedBottom = Origin(selectedNamePlate).Y + selectedNamePlate.ActualHeight;
            var mixerBottom = Origin(mixerNamePlate).Y + mixerNamePlate.ActualHeight;
            Assert(Math.Abs(selectedBottom - mixerBottom) <= 6, "channel-strip-bottom-aligned");
            channelAlignment = new { selected_nameplate_bottom = selectedBottom, mixer_nameplate_bottom = mixerBottom };
            stage = "capture-window-visual";
            await Capture("native-app-visual.png");
            RefreshWorkspaceReceipt();
            checks.Add("window-visual-artifact-written"); stage = "completed";
        }
        void RecordTimingState(string name, string context, bool rejectEdits)
        {
            UpdateLayout();
            var before = SessionHash();
            _ = MeasureTimingMarkers(context);
            if (rejectEdits)
            {
                foreach (var button in new[] { MoveButton, TrimButton })
                {
                    try { ((IInvokeProvider)new ButtonAutomationPeer(button).GetPattern(PatternInterface.Invoke)).Invoke(); throw new InvalidOperationException("Unavailable event timing accepted an edit."); }
                    catch (System.Windows.Automation.ElementNotEnabledException) { }
                }
                Key(MoveBox, System.Windows.Input.Key.Enter); Key(MoveBox, System.Windows.Input.Key.Escape);
                Key(TrimBox, System.Windows.Input.Key.Enter); Key(TrimBox, System.Windows.Input.Key.Escape);
            }
            var after = SessionHash();
            if (before != after) throw new InvalidOperationException("Inspecting unavailable event timing changed the shared session.");
            topRowsStates.Add(new { name, before_sha256 = before, after_sha256 = after, revision = model.State.Revision,
                selected_track_id = model.State.Selection.TrackID, selected_clip_id = model.State.Selection.ClipID,
                markers = MeasureTimingMarkers(context), layout = MeasureTopRowsLayout() });
        }
        object RulerBox(Rect rect) => new { text = Timeline.RulerCornerLabel.Text, x = rect.X, y = rect.Y, width = rect.Width, height = rect.Height };
        void ValidateRulerCorner(Rect label, Rect header)
        {
            var viewport = BoundsOf(Descendants<ScrollContentPresenter>(TimelineScroll).Single(presenter => ReferenceEquals(presenter.TemplatedParent, TimelineScroll)));
            if (Timeline.RulerCornerLabel.Text != "Bars + Beats" || !Timeline.RulerCornerLabel.IsVisible || label.Width <= 0 || label.Height <= 0 ||
                label.Left < header.Left - 0.5 || label.Right > header.Right + 0.5 || label.Top < viewport.Top - 0.5 || label.Bottom > header.Top + 0.5)
                throw new InvalidOperationException("The musical ruler corner is not visible inside its pinned header region.");
        }
        async Task LongNamesScenario()
        {
            stage = "top-rows-long-names";
            var originalRoot = Path.Combine(AppContext.BaseDirectory, "Examples", "Rebase Preview.rebaseproj");
            var originalBytes = await File.ReadAllBytesAsync(Path.Combine(originalRoot, "Project.json"));
            var project = JsonNode.Parse(originalBytes)?.AsObject() ?? throw new InvalidDataException("The bundled project is not an object.");
            const string projectName = "Authored long project name — arrangement and source information remain separate — " +
                "a readable complete project identity available from the tooltip while the compact status row retains its clock, track count and media context";
            const string eventName = "Authored long event name — independent selected event identity — " +
                "start and end remain accessible without allowing the full title to displace the timing fields or the source offset";
            project["name"] = projectName;
            var firstClip = project["tracks"]![0]!["clips"]![0]!.AsObject();
            firstClip["name"] = eventName;
            var clipID = firstClip["id"]!.GetValue<string>();
            var destination = Path.Combine(work, "LongNames.rebaseproj"); Directory.CreateDirectory(destination);
            foreach (var file in Directory.EnumerateFiles(originalRoot, "*", SearchOption.AllDirectories))
            {
                var relative = Path.GetRelativePath(originalRoot, file);
                if (relative == "Project.json") continue;
                var target = Path.Combine(destination, relative); Directory.CreateDirectory(Path.GetDirectoryName(target)!); File.Copy(file, target);
            }
            var derivedBytes = JsonSerializer.SerializeToUtf8Bytes(project, new JsonSerializerOptions { WriteIndented = true });
            await File.WriteAllBytesAsync(Path.Combine(destination, "Project.json"), derivedBytes);
            await model.Open(destination, true, true);
            await model.Command("selectClip", clipID: clipID);
            await Until(() => !model.Busy && model.SelectedClip?.Name == eventName && Timeline.PopulatedWaveformCount == model.Project!.Tracks.Sum(track => track.Clips.Length), stage);
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            if (ProjectName.Text != projectName || SelectionName.Text != eventName) throw new InvalidOperationException("The long-name control was not selected.");
            object TextReceipt(TextBlock text)
            {
                var box = BoundsOf(text);
                var measured = new FormattedText(text.Text, System.Globalization.CultureInfo.CurrentCulture, text.FlowDirection,
                    new Typeface(text.FontFamily, text.FontStyle, text.FontWeight, text.FontStretch), text.FontSize, text.Foreground, VisualTreeHelper.GetDpi(text).PixelsPerDip);
                if (text.TextTrimming != TextTrimming.CharacterEllipsis || text.ToolTip as string != text.Text || measured.WidthIncludingTrailingWhitespace <= box.Width || box.Width <= 0)
                    throw new InvalidOperationException("A long title lacks bounded ellipsis and a complete tooltip.");
                return new { text = text.Text, tooltip = (string)text.ToolTip, trimming = text.TextTrimming.ToString(), natural_width = measured.WidthIncludingTrailingWhitespace,
                    x = box.X, y = box.Y, width = box.Width, height = box.Height };
            }
            topRowsLongNames = new { project_name = projectName, event_name = eventName, project_text = TextReceipt(ProjectName), event_text = TextReceipt(SelectionName),
                original_manifest_sha256 = Hash(originalBytes), derived_manifest_sha256 = Hash(derivedBytes) };
            _ = MeasureTopRowsLayout();
            await CaptureTopRows("native-top-rows-long-names-visual.png");
            checks.Add("top-rows-long-names");
            stage = "top-rows-resize-preserves-state";
            var before = SessionHash(); var revisionBefore = model.State.Revision;
            var trackBefore = model.State.Selection.TrackID; var clipBefore = model.State.Selection.ClipID;
            var widthBefore = ActualWidth; var heightBefore = ActualHeight;
            Width = 1400;
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            var widthAfter = ActualWidth;
            await CaptureTopRows("native-top-rows-wide-visual.png");
            var after = SessionHash();
            topRowsResize = new { before_sha256 = before, after_sha256 = after, revision_before = revisionBefore, revision_after = model.State.Revision,
                track_before = trackBefore, track_after = model.State.Selection.TrackID, clip_before = clipBefore, clip_after = model.State.Selection.ClipID,
                requested_outer_width = 1400, outer_width_before = widthBefore, outer_width_after = widthAfter, wider_observed = widthAfter > widthBefore + 0.5 };
            if (before != after || revisionBefore != model.State.Revision || trackBefore != model.State.Selection.TrackID || clipBefore != model.State.Selection.ClipID)
                throw new InvalidOperationException("Window resizing changed the shared session.");
            Width = widthBefore; Height = heightBefore;
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            MeasureWindowBounds();
            if (Math.Abs(ActualWidth - widthBefore) > 0.5 || Math.Abs(ActualHeight - heightBefore) > 0.5 || before != SessionHash())
                throw new InvalidOperationException("Restoring the measured window bounds changed the layout or project state.");
            checks.Add("top-rows-resize-preserves-state");
            string Hash(byte[] bytes) => Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes)).ToLowerInvariant();
        }
        async Task CaptureTopRows(string filename)
        {
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            var layout = MeasureTopRowsLayout();
            await Capture(filename);
            topRowsCaptures.Add(new { screenshot = filename, png_sha256 = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(await File.ReadAllBytesAsync(Path.Combine(root, filename)))).ToLowerInvariant(),
                window_bounds = windowBounds, layout });
        }
        string SessionHash() => Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(JsonSerializer.Serialize(model.State, ProtocolJson.Options)))).ToLowerInvariant();
        Rect BoundsOf(FrameworkElement element) => element.IsVisible ? element.TransformToAncestor((FrameworkElement)Content).TransformBounds(new Rect(element.RenderSize)) : new Rect(0, 0, 0, 0);
        static object Box(Rect rectangle) => new { x = rectangle.X, y = rectangle.Y, width = rectangle.Width, height = rectangle.Height };
        void RefreshWorkspaceReceipt()
        {
            workspaceReceipt = new { initial_state_sha256 = workspaceInitialHash, states = workspaceStates, event_targets = workspaceTargets,
                splitter = workspaceSplitter, source_only = workspaceSourceOnly, capture_safety = workspaceCaptureSafety,
                current_layout = new { selected_density_index = RowDensityBox.SelectedIndex, row_height = Timeline.RowHeight,
                    layout_capture_active = LayoutCaptureActive, density_dropdown_open = RowDensityBox.IsDropDownOpen,
                    viewport_height = TimelineScroll.ViewportHeight, viewport_width = TimelineScroll.ViewportWidth,
                    tracks_bottom = Timeline.TracksBottom, extent_height = TimelineScroll.ExtentHeight,
                    scrollable_height = TimelineScroll.ScrollableHeight, vertical_offset = TimelineScroll.VerticalOffset,
                    arrangement_height = ArrangementRow.ActualHeight, mixer_height = MixerRow.ActualHeight },
                toolbar_controls = new[] { (FrameworkElement)RowDensityBox, LeftZoneToggle, MixerZoneToggle }.Select(control => new { name = control.Name,
                    x = BoundsOf(control).X, y = BoundsOf(control).Y, width = control.ActualWidth, height = control.ActualHeight }).ToArray(),
                screenshots = new { normal = "native-workspace-normal-visual.png", expanded = "native-workspace-expanded-visual.png" },
                input_evidence = "UIA and injected routed keyboard events; no physical input" };
        }
        async Task WorkspaceScenario()
        {
            workspaceInitialHash = SessionHash();
            void Record(string name)
            {
                workspaceStates.Add(new { name, state_sha256 = SessionHash(), revision = model.State.Revision,
                    selected_track_id = model.State.Selection.TrackID, selected_clip_id = model.State.Selection.ClipID,
                    row_height = Timeline.RowHeight, selected_density_index = RowDensityBox.SelectedIndex,
                    viewport_height = TimelineScroll.ViewportHeight, viewport_width = TimelineScroll.ViewportWidth,
                    canvas_width = Timeline.Width, divider_ends = Timeline.RowDividers.Select(line => new { x1 = line.X1, y1 = line.Y1, x2 = line.X2, y2 = line.Y2 }).ToArray(),
                    tracks_bottom = Timeline.TracksBottom, extent_height = TimelineScroll.ExtentHeight,
                    scrollable_height = TimelineScroll.ScrollableHeight, vertical_offset = TimelineScroll.VerticalOffset,
                    left_visible = leftZoneVisible, mixer_visible = mixerZoneVisible,
                    left_width = ChannelColumn.ActualWidth + InspectorColumn.ActualWidth, horizontal_offset = TimelineScroll.HorizontalOffset,
                    timeline = Box(BoundsOf(TimelineScroll)), viewport = Box(BoundsOf(Descendants<ScrollContentPresenter>(TimelineScroll).Single(presenter => ReferenceEquals(presenter.TemplatedParent, TimelineScroll)))),
                    mixer = Box(BoundsOf(MixerZone)), headers = Timeline.TrackHeaders.Select(header => Box(BoundsOf(header))).ToArray() });
                RefreshWorkspaceReceipt();
                if (Timeline.RowDividers.Count != 4 || Timeline.RowDividers.Any(line => Math.Abs(line.X2 - Timeline.Width) > 0.5 || line.Y1 != line.Y2) ||
                    Timeline.RowDividers.Select(line => line.Y1).Distinct().Count() != 4)
                    throw new InvalidOperationException("The track row dividers do not fill the actual canvas width.");
                var expectedExtent = Math.Max(TimelineScroll.ViewportHeight, Timeline.TracksBottom);
                if (Math.Abs(TimelineScroll.ExtentHeight - expectedExtent) > 0.5 || Math.Abs(TimelineScroll.ScrollableHeight - Math.Max(0, Timeline.TracksBottom - TimelineScroll.ViewportHeight)) > 0.5)
                    throw new InvalidOperationException("The timeline extent does not match its measured viewport and track rows.");
                if (SessionHash() != workspaceInitialHash) throw new InvalidOperationException("A workspace presentation change modified the shared project state.");
            }
            void CheckRowsAndTargets()
            {
                var rows = Timeline.TrackHeaders;
                if (rows.Count != 4 || rows.Any(row => Math.Abs(row.ActualHeight - Timeline.RowHeight) > 0.5)) throw new InvalidOperationException("Track row density does not match actual row geometry.");
                for (var i = 0; i < rows.Count; i++)
                {
                    if (i > 0 && Math.Abs(BoundsOf(rows[i]).Y - BoundsOf(rows[i - 1]).Y - Timeline.RowHeight) > 0.5) throw new InvalidOperationException("Track row baselines are inconsistent.");
                    foreach (var control in Descendants<Control>(rows[i]).Where(control => control is Button or CheckBox))
                    {
                        var box = control.TransformToAncestor(rows[i]).TransformBounds(new Rect(control.RenderSize));
                        if (box.Top < 0 || box.Bottom > rows[i].ActualHeight + 0.5) throw new InvalidOperationException("Track controls overflow their row.");
                    }
                }
                var button = Timeline.Children.OfType<Button>().First();
                bool Hit(Point point)
                {
                    DependencyObject? target = button.InputHitTest(point) as DependencyObject;
                    while (target is not null && target != button) target = VisualTreeHelper.GetParent(target);
                    return target == button;
                }
                var moveX = button.ActualWidth / 2; var trimX = button.ActualWidth - TimelineView.TrimHitWidth / 2;
                var moveHit = Hit(new Point(moveX, button.ActualHeight / 2)); var trimHit = Hit(new Point(trimX, button.ActualHeight / 2));
                if (!moveHit || !trimHit || button.ActualHeight < 30 || moveX >= button.ActualWidth - TimelineView.TrimHitWidth)
                    throw new InvalidOperationException("Event move and trim hit areas are not usable.");
                workspaceTargets.Add(new { row_height = Timeline.RowHeight, event_width = button.ActualWidth, event_height = button.ActualHeight,
                    move_x = moveX, trim_x = trimX, trim_width = TimelineView.TrimHitWidth, move_hit = moveHit, trim_hit = trimHit });
            }
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            stage = "workspace-compact-default"; Record("compact");
            Assert(Timeline.RowHeight == 44 && RowDensityBox.SelectedIndex == 0 && TimelineScroll.ViewportHeight >= Timeline.TracksBottom, "workspace-compact-default");
            CheckRowsAndTargets();
            stage = "workspace-normal-density";
            await SelectComboItem(RowDensityBox, 1);
            await Capture("native-workspace-normal-visual.png"); Record("normal");
            CheckRowsAndTargets();
            Assert(Timeline.RowHeight == 68 && TimelineScroll.ViewportHeight >= Timeline.TracksBottom, "workspace-normal-density");
            await Until(() => Timeline.PopulatedWaveformCount == model.Project!.Tracks.Sum(track => track.Clips.Length), "workspace-normal-waveforms");
            await Capture("native-workspace-normal-visual.png");
            await SelectComboItem(RowDensityBox, 0);
            checks.Add("workspace-event-hit-targets");

            var section = (IExpandCollapseProvider)new ExpanderAutomationPeer(EventEditingSection).GetPattern(PatternInterface.ExpandCollapse);
            section.Collapse(); await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            if (SplitInspectorButton.IsVisible || DeleteInspectorButton.IsVisible) throw new InvalidOperationException("Collapsed event section still displays actions.");
            section.Expand(); await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            Assert(SplitInspectorButton.IsVisible && DeleteInspectorButton.IsVisible && SessionHash() == workspaceInitialHash, "workspace-inspector-sections");

            foreach (var (name, target) in new (string, UIElement)[] { ("inspector", InspectorGainSlider), ("timeline", Timeline.Children.OfType<Button>().First()), ("mixer", mixerSliders[model.SelectedTrack!.Id + ":gain"]) })
            {
                if (!target.CaptureMouse()) throw new InvalidOperationException("Could not establish the programmatic capture control.");
                try
                {
                    Toggle(LeftZoneToggle); Toggle(MixerZoneToggle); RowDensityBox.SelectedIndex = 1;
                    var retained = target.IsMouseCaptured;
                    if (!retained || !leftZoneVisible || !mixerZoneVisible || Timeline.RowHeight != 44 || RowDensityBox.SelectedIndex != 0)
                        throw new InvalidOperationException("A layout change interrupted an active control capture.");
                    workspaceCaptureSafety.Add(new { surface = name, capture_before = true, capture_after = retained, layout_refused = true });
                }
                finally { target.ReleaseMouseCapture(); }
            }
            checks.Add("workspace-active-capture-preserved");
            SpaceToggle(LeftZoneToggle); await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle); Record("left-hidden");
            if (leftZoneVisible || ChannelColumn.ActualWidth != 0 || InspectorColumn.ActualWidth != 0) throw new InvalidOperationException("Hiding the left zone left occupied columns.");
            SpaceToggle(MixerZoneToggle); await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle); Record("panes-hidden");
            if (mixerZoneVisible || MixerRow.ActualHeight != 0 || MixerDividerRow.ActualHeight != 0) throw new InvalidOperationException("Hiding the lower zone left occupied rows.");
            await Capture("native-workspace-expanded-visual.png");
            SpaceToggle(LeftZoneToggle); SpaceToggle(MixerZoneToggle); await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle); Record("restored");
            Assert(leftZoneVisible && mixerZoneVisible && SessionHash() == workspaceInitialHash, "workspace-keyboard-pane-toggles");
            checks.Add("workspace-pane-state-preserved");

            var initialMixerHeight = MixerRow.ActualHeight;
            MixerSplitter.Focus();
            for (var i = 0; i < 60; i++) SplitterKey(System.Windows.Input.Key.Down);
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            var minimum = MixerRow.ActualHeight; Record("splitter-minimum"); MeasureFader();
            for (var i = 0; i < 60; i++) SplitterKey(System.Windows.Input.Key.Up);
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            var maximum = MixerRow.ActualHeight; var arrangementMinimum = ArrangementRow.ActualHeight; Record("splitter-maximum"); MeasureFader();
            Assert(Math.Abs(minimum - MixerRow.MinHeight) <= 0.5 && Math.Abs(maximum - MixerRow.MaxHeight) <= 0.5 &&
                maximum > minimum && arrangementMinimum >= 219.5 && MixerSplitter.IsKeyboardFocused, "workspace-splitter-bounds");
            workspaceSplitter = new { minimum_height = MixerRow.MinHeight, maximum_height = MixerRow.MaxHeight, minimum_actual = minimum,
                maximum_actual = maximum, arrangement_minimum_actual = arrangementMinimum, keyboard_focus_preserved = MixerSplitter.IsKeyboardFocused, faders = workspaceFaders };
            MixerRow.Height = new GridLength(initialMixerHeight); savedMixerHeight = initialMixerHeight;
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle); Record("splitter-restored");
            checks.Add("workspace-resized-fader-geometry"); checks.Add("workspace-visual-artifacts");

            void MeasureFader()
            {
                var slider = mixerSliders[model.SelectedTrack!.Id + ":gain"];
                var scale = Descendants<FaderScale>(Mixer.Children[0]).Single();
                var track = (Track)slider.Template.FindName("PART_Track", slider);
                var thumbY = track.Thumb.TranslatePoint(new Point(track.Thumb.ActualWidth / 2, track.Thumb.ActualHeight / 2), scale).Y;
                var tickY = scale.TickY(slider.Value) ?? throw new InvalidOperationException("The resized fader has no scale geometry.");
                var plate = Descendants<Button>(Mixer.Children[0]).Single();
                var plateBox = plate.TransformToAncestor(MixerScroll).TransformBounds(new Rect(plate.RenderSize));
                if (Math.Abs(tickY - thumbY) > 0.5 || plateBox.Top < 0 || plateBox.Bottom > MixerScroll.ActualHeight + 0.5)
                    throw new InvalidOperationException("Resizing the mixer clipped a nameplate or misaligned a fader scale.");
                workspaceFaders.Add(new { zone_height = MixerRow.ActualHeight, fader_height = slider.ActualHeight, value = slider.Value, tick_y = tickY, thumb_y = thumbY });
            }
            void SplitterKey(Key key)
            {
                MixerSplitter.RaiseEvent(new KeyEventArgs(Keyboard.PrimaryDevice, PresentationSource.FromVisual(this), Environment.TickCount, key) { RoutedEvent = Keyboard.KeyDownEvent });
                UpdateLayout();
            }
            void SpaceToggle(CheckBox control)
            {
                control.Focus();
                var preview = new KeyEventArgs(Keyboard.PrimaryDevice, PresentationSource.FromVisual(this), Environment.TickCount, System.Windows.Input.Key.Space) { RoutedEvent = Keyboard.PreviewKeyDownEvent };
                control.RaiseEvent(preview);
                if (preview.Handled) throw new InvalidOperationException("Transport consumed Space intended for a workspace toggle.");
                control.RaiseEvent(new KeyEventArgs(Keyboard.PrimaryDevice, PresentationSource.FromVisual(this), Environment.TickCount, System.Windows.Input.Key.Space) { RoutedEvent = Keyboard.KeyDownEvent });
                control.RaiseEvent(new KeyEventArgs(Keyboard.PrimaryDevice, PresentationSource.FromVisual(this), Environment.TickCount, System.Windows.Input.Key.Space) { RoutedEvent = Keyboard.KeyUpEvent });
            }
        }
        Point Origin(FrameworkElement element) => element.TransformToAncestor(this).Transform(new Point());
        async Task<(string Path, string ControlTrackID, object Receipt)> MakeSourceSelectionFixture()
        {
            var originalRoot = Path.GetFileName(sourceProject) == "Project.json" ? Path.GetDirectoryName(sourceProject)! : sourceProject!;
            var originalBytes = await File.ReadAllBytesAsync(Path.Combine(originalRoot, "Project.json"));
            var project = JsonNode.Parse(originalBytes)?.AsObject() ?? throw new InvalidDataException("The authored source fixture is not an object.");
            var tracks = project["tracks"]?.AsArray() ?? throw new InvalidDataException("The authored source fixture has no tracks.");
            if (tracks.Count != 1 || tracks[0]?["unresolvedAudioEvents"]?.AsArray().Count != 1)
                throw new InvalidDataException("The source selection control requires the locked one-track, one-event fixture.");
            const string trackID = "D22D4F70-A97C-4CCD-A3CD-23D0629365F4";
            if (tracks[0]?["id"]?.GetValue<string>() == trackID) throw new InvalidDataException("Selection control track identity collides with the fixture.");
            tracks.Add(new JsonObject { ["id"] = trackID, ["name"] = "Selection control (authored)", ["gainDB"] = 0, ["pan"] = 0,
                ["isMuted"] = false, ["isSolo"] = false, ["timeBase"] = "seconds", ["clips"] = new JsonArray(),
                ["automation"] = new JsonArray(), ["unresolvedAudioEvents"] = new JsonArray() });
            var derivedRoot = Path.Combine(work, "SourceSelectionControl.rebaseproj"); Directory.CreateDirectory(derivedRoot);
            var sidecars = new List<object>();
            foreach (var file in Directory.EnumerateFiles(originalRoot, "*", SearchOption.AllDirectories))
            {
                var relative = Path.GetRelativePath(originalRoot, file);
                if (relative == "Project.json") continue;
                var destination = Path.Combine(derivedRoot, relative); Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                File.Copy(file, destination);
                var before = FileHash(file); var after = FileHash(destination);
                if (before != after) throw new IOException("A source selection control sidecar was not preserved.");
                sidecars.Add(new { path = relative.Replace('\\', '/'), original_sha256 = before, copied_sha256 = after });
            }
            var bytes = JsonSerializer.SerializeToUtf8Bytes(project, new JsonSerializerOptions { WriteIndented = true });
            await File.WriteAllBytesAsync(Path.Combine(derivedRoot, "Project.json"), bytes);
            string Hash(byte[] value) => Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(value)).ToLowerInvariant();
            string FileHash(string path) => Hash(File.ReadAllBytes(path));
            var originalHash = Hash(originalBytes);
            if (FileHash(Path.Combine(originalRoot, "Project.json")) != originalHash) throw new IOException("The original source fixture changed during the control.");
            return (derivedRoot, trackID, new { kind = "authored scratch project with one empty selection-control track",
                original_manifest_sha256 = originalHash, derived_manifest_sha256 = Hash(bytes), original_track_count = 1,
                derived_track_count = 2, retained_event_count = 1, sidecars });
        }
        async Task CPRImportScenario()
        {
            var package = Path.GetFileName(sourceProject) == "Project.json" ? Path.GetDirectoryName(sourceProject)! : sourceProject!;
            var original = await File.ReadAllBytesAsync(Path.Combine(package, "Compatibility", "CPR", "Original.cpr"));
            var source = Path.Combine(work, "AuthoredSource.cpr"); await File.WriteAllBytesAsync(source, original);
            var hash = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(original)).ToLowerInvariant();
            smokeCPRPath = source;
            string StateIdentity() => JsonSerializer.Serialize(model.State, ProtocolJson.Options);
            async Task<CPRReviewWindow> OpenReview(bool historical = false)
            {
                var menu = historical ? ImportReportMenu : ImportCPRMenu;
                ((IInvokeProvider)new MenuItemAutomationPeer(menu).GetPattern(PatternInterface.Invoke)).Invoke();
                await Until(() => activeCPRReview is { IsVisible: true } && !model.Busy, "cpr-review-open");
                await Dispatcher.InvokeAsync(() => activeCPRReview!.UpdateLayout(), DispatcherPriority.ApplicationIdle);
                return activeCPRReview!;
            }
            async Task CloseReview(CPRReviewWindow review)
            {
                await Invoke(review.CloseButton);
                await Until(() => activeCPRReview is null && !model.Busy && IsEnabled, "cpr-review-close");
            }
            var before = StateIdentity(); stage = "cpr-review-window-visible";
            var review = await OpenReview();
            Assert(review.IsVisible && !IsEnabled && review.ImportButton.IsEnabled && review.Review.SourceSHA256 == hash &&
                review.Review.SourceName == "AuthoredSource.cpr", "cpr-review-window-visible");
            var pagesChecked = 0; var itemsChecked = 0; var verticalScrollChecked = false;
            do
            {
                pagesChecked++; itemsChecked += review.CurrentPage.Items.Length;
                await Dispatcher.InvokeAsync(review.UpdateLayout, DispatcherPriority.ApplicationIdle);
                if (review.ReviewScroll.ScrollableHeight > 0)
                {
                    var provider = (IScrollProvider)new ScrollViewerAutomationPeer(review.ReviewScroll).GetPattern(PatternInterface.Scroll);
                    provider.SetScrollPercent(System.Windows.Automation.ScrollPatternIdentifiers.NoScroll, 100);
                    await Dispatcher.InvokeAsync(review.UpdateLayout, DispatcherPriority.ApplicationIdle);
                    var last = review.LastReviewItem;
                    var bottom = last.TransformToAncestor(review.ReviewScroll).TransformBounds(new Rect(last.RenderSize));
                    if (bottom.Bottom <= 0 || bottom.Top >= review.ReviewScroll.ActualHeight) throw new InvalidOperationException("The last review item is not reachable by scrolling.");
                    verticalScrollChecked = true;
                    provider.SetScrollPercent(System.Windows.Automation.ScrollPatternIdentifiers.NoScroll, 0);
                }
                if (review.CurrentPage.NextOffset is not { } next) break;
                await Invoke(review.NextButton);
                await Until(() => !review.Working && review.CurrentPage.Offset == next, "cpr-review-next-page");
            } while (true);
            Assert(itemsChecked == review.Review.TotalItems && !review.NextButton.IsEnabled && pagesChecked > 0, "cpr-review-all-pages-accessible");
            while (review.PreviousButton.IsEnabled) await Invoke(review.PreviousButton);
            var (reviewBounds, reviewLayout) = await CaptureCPRReview(review, "native-cpr-review-visual.png");
            checks.Add("cpr-review-footer-visible"); checks.Add("cpr-review-capture-alpha-coverage");
            checks.Add("cpr-review-visual-artifact");
            await CloseReview(review);
            Assert(StateIdentity() == before && model.CPRReview is null, "cpr-review-cancel-preserves-session");

            stage = "cpr-changed-source-rejected"; review = await OpenReview();
            var changed = (byte[])original.Clone(); var marker = System.Text.Encoding.UTF8.GetBytes("Authored");
            var markerAt = Enumerable.Range(0, original.Length - marker.Length + 1).First(i => original.AsSpan(i, marker.Length).SequenceEqual(marker));
            changed[markerAt] = (byte)'B'; await File.WriteAllBytesAsync(source, changed);
            var changedDestination = Path.Combine(work, "Changed.rebaseproj"); smokeCPRDestination = () => changedDestination;
            await Invoke(review.ImportButton);
            await Until(() => !review.Working && !model.Busy && review.ReviewMessage.Length > 0, stage);
            Assert(review.IsVisible && StateIdentity() == before && !Directory.Exists(changedDestination) &&
                model.Status.Contains("changed", StringComparison.OrdinalIgnoreCase), "cpr-changed-source-rejected");
            review.Width = review.MinWidth; review.Height = review.MinHeight;
            var (minimumErrorBounds, minimumErrorLayout) = await CaptureCPRReview(review, "native-cpr-review-minimum-error-visual.png");
            Assert(review.ReviewMessage.Length > 0 && review.ImportButton.IsEnabled && review.ErrorScroll.ActualHeight is > 0 and <= 80,
                "cpr-review-minimum-error-layout");
            var errorScrollable = review.ErrorScroll.ScrollableHeight > 0;
            if (errorScrollable)
            {
                var provider = (IScrollProvider)new ScrollViewerAutomationPeer(review.ErrorScroll).GetPattern(PatternInterface.Scroll);
                provider.SetScrollPercent(System.Windows.Automation.ScrollPatternIdentifiers.NoScroll, 100);
                await Dispatcher.InvokeAsync(review.UpdateLayout, DispatcherPriority.ApplicationIdle);
                if (Math.Abs(review.ErrorScroll.VerticalOffset - review.ErrorScroll.ScrollableHeight) > 0.5)
                    throw new InvalidOperationException("The complete review error is not reachable by scrolling.");
            }
            await CloseReview(review); await File.WriteAllBytesAsync(source, original);

            stage = "cpr-dirty-cancel-preserves-session";
            var track = model.Project!.Tracks[0]; await model.Command("setGain", trackID: track.Id, value: track.GainDB + 0.5);
            var dirty = StateIdentity(); var destinationRequested = false;
            review = await OpenReview(); smokeCPRDirtyDecision = () => MessageBoxResult.Cancel;
            smokeCPRDestination = () => { destinationRequested = true; return null; };
            await Invoke(review.ImportButton); await Until(() => !review.Working && review.ReviewMessage.Length > 0, stage);
            Assert(model.State.Dirty && StateIdentity() == dirty && review.IsVisible && !destinationRequested, "cpr-dirty-cancel-preserves-session");
            stage = "cpr-destination-cancel-preserves-review";
            smokeCPRDirtyDecision = () => MessageBoxResult.No;
            await Invoke(review.ImportButton); await Until(() => !review.Working && destinationRequested, stage);
            Assert(StateIdentity() == dirty && review.IsVisible && model.CPRReview?.ReviewID == review.Review.ReviewID, "cpr-destination-cancel-preserves-review");

            stage = "cpr-import-supported-data";
            var imported = Path.Combine(work, "Imported.rebaseproj"); smokeCPRDestination = () => imported;
            await Invoke(review.ImportButton); await Until(() => activeCPRReview is null && !model.Busy && IsEnabled, stage);
            Assert(!model.State.Dirty && !model.State.NeedsSaveAs && !model.State.CanUndo && model.CPRReview is null &&
                model.State.Path == imported && model.SourceEvents.Length == 1, "cpr-import-supported-data");
            var preserved = await File.ReadAllBytesAsync(Path.Combine(imported, "Compatibility", "CPR", "Original.cpr"));
            Assert(preserved.SequenceEqual(original) && (await File.ReadAllBytesAsync(source)).SequenceEqual(original), "cpr-import-source-preserved");
            stage = "cpr-historical-report-readonly"; var importedIdentity = StateIdentity();
            var historical = await OpenReview(historical: true);
            Assert(historical.Review.Historical && !historical.ImportButton.IsEnabled && historical.Review.SourceSHA256 == hash && StateIdentity() == importedIdentity, "cpr-historical-report-readonly");
            await CloseReview(historical);
            if (StateIdentity() != importedIdentity) throw new InvalidOperationException("Closing the historical report changed the project.");
            cprReviewReceipt = new { reviewed = true, cancelled_without_changes = true, changed_source_rejected = true, dirty_guard = true,
                destination_cancel_preserved_review = true, imported = true, historical_read_only = true, preserved_source_sha256 = hash,
                review_screenshot = "native-cpr-review-visual.png", window_bounds = reviewBounds, pages_checked = pagesChecked, items_checked = itemsChecked,
                capture_layout = reviewLayout, minimum_error_screenshot = "native-cpr-review-minimum-error-visual.png",
                minimum_error_bounds = minimumErrorBounds, minimum_error_layout = minimumErrorLayout, error_scrolling_checked = errorScrollable,
                vertical_scroll_checked = verticalScrollChecked, dark_caption_hresult = review.DarkCaptionResult, native_frame_visual_tested = false,
                native_file_pickers_tested = false, physical_input_tested = false };
            smokeCPRPath = null; smokeCPRDestination = null; smokeCPRDirtyDecision = null;
        }
        async Task<(object Bounds, object Layout)> CaptureCPRReview(CPRReviewWindow review, string filename)
        {
            await Dispatcher.InvokeAsync(review.UpdateLayout, DispatcherPriority.ApplicationIdle);
            var client = review.Content as Border ?? throw new InvalidOperationException("The CPR review has no full client root.");
            if (client.Margin != new Thickness(0) || client.Background is not SolidColorBrush background || background.Color.A != 255)
                throw new InvalidOperationException("The CPR review capture root must be marginless and opaque.");
            var controls = new List<object>();
            foreach (var button in new[] { review.PreviousButton, review.NextButton, review.CloseButton, review.ImportButton })
            {
                var box = button.TransformToAncestor(client).TransformBounds(new Rect(button.RenderSize));
                if (!button.IsVisible || box.Width <= 0 || box.Height <= 0 || box.Left < 0 || box.Top < 0 ||
                    box.Right > client.ActualWidth + 0.5 || box.Bottom > client.ActualHeight + 0.5)
                    throw new InvalidOperationException("A CPR review footer control is outside the captured client surface.");
                controls.Add(new { name = System.Windows.Automation.AutomationProperties.GetName(button), x = box.X, y = box.Y, width = box.Width, height = box.Height });
            }
            if (review.ReviewScroll.ActualHeight < 40) throw new InvalidOperationException("The review content viewport is not usable.");
            var dpi = VisualTreeHelper.GetDpi(review);
            var bounds = new { outer_width = review.ActualWidth, outer_height = review.ActualHeight, client_width = client.ActualWidth,
                client_height = client.ActualHeight, dpi_x = dpi.PixelsPerInchX, dpi_y = dpi.PixelsPerInchY };
            var width = (int)Math.Ceiling(client.ActualWidth); var height = (int)Math.Ceiling(client.ActualHeight);
            var picture = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32);
            picture.Render(client);
            var pixels = new byte[checked(width * height * 4)]; picture.CopyPixels(pixels, width * 4, 0);
            var alphaMinimum = 255; var alpha254 = 0; var alpha255 = 0; var alphaBelow254 = 0;
            for (var i = 3; i < pixels.Length; i += 4)
            {
                var alpha = pixels[i]; alphaMinimum = Math.Min(alphaMinimum, alpha);
                if (alpha == 255) alpha255++; else if (alpha == 254) alpha254++; else alphaBelow254++;
            }
            var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(picture));
            var imagePath = Path.Combine(root, filename);
            using (var output = File.Create(imagePath)) encoder.Save(output);
            var layout = new { footer_controls = controls, alpha_minimum = alphaMinimum, alpha_254_pixels = alpha254, alpha_255_pixels = alpha255,
                alpha_below_254_pixels = alphaBelow254, total_pixels = width * height,
                review_viewport_height = review.ReviewScroll.ActualHeight, error_characters = review.ReviewMessage.Length };
            var diagnostic = new { schema = 1, screenshot = filename, png_sha256 = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(await File.ReadAllBytesAsync(imagePath))).ToLowerInvariant(),
                root_background_alpha = background.Color.A, window_bounds = bounds, capture_layout = layout };
            // Keep failed captures inspectable. WPF captures already measured in
            // this project contain alpha 254 as well as 255; actual holes do not.
            await File.WriteAllTextAsync(Path.Combine(root, Path.GetFileNameWithoutExtension(filename) + "-alpha.json"), JsonSerializer.Serialize(diagnostic, new JsonSerializerOptions { WriteIndented = true }));
            if (alphaBelow254 != 0) throw new InvalidOperationException("The CPR review capture contains pixels below alpha 254; inspect the retained alpha diagnostic.");
            return (bounds, layout);
        }
        CheckBox MixerFlag(string name) => Descendants<CheckBox>(Mixer).Single(control => System.Windows.Automation.AutomationProperties.GetName(control) == name);
        async Task Capture(string filename)
        {
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            var client = MeasureWindowBounds();
            var image = new RenderTargetBitmap((int)Math.Ceiling(client.ActualWidth), (int)Math.Ceiling(client.ActualHeight), 96, 96, PixelFormats.Pbgra32);
            image.Render(client);
            var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(image));
            using var output = File.Create(Path.Combine(root, filename)); encoder.Save(output);
        }
        FrameworkElement MeasureWindowBounds()
        {
            var client = Content as FrameworkElement ?? throw new InvalidOperationException("The window has no client visual.");
            var dpi = VisualTreeHelper.GetDpi(this);
            windowBounds = new { outer_width = ActualWidth, outer_height = ActualHeight, client_width = client.ActualWidth, client_height = client.ActualHeight, dpi_x = dpi.PixelsPerInchX, dpi_y = dpi.PixelsPerInchY };
            return client;
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
        static IRangeValueProvider RangeValue(Slider slider) => (IRangeValueProvider)(UIElementAutomationPeer.CreatePeerForElement(slider)
            ?? throw new InvalidOperationException("Slider has no automation peer.")).GetPattern(PatternInterface.RangeValue);
        void Key(UIElement control, Key key)
        {
            var args = new KeyEventArgs(Keyboard.PrimaryDevice, PresentationSource.FromVisual(this), Environment.TickCount, key) { RoutedEvent = Keyboard.PreviewKeyDownEvent };
            control.RaiseEvent(args);
        }
        static void Toggle(CheckBox control) => ((IToggleProvider)new CheckBoxAutomationPeer(control).GetPattern(PatternInterface.Toggle)).Toggle();
        async Task SelectComboItem(ComboBox control, int index)
        {
            var peer = new ComboBoxAutomationPeer(control);
            var expand = (IExpandCollapseProvider)peer.GetPattern(PatternInterface.ExpandCollapse);
            expand.Expand(); await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            var item = peer.GetChildren()?.Select(child => child.GetPattern(PatternInterface.SelectionItem)).OfType<ISelectionItemProvider>().ElementAt(index)
                ?? throw new InvalidOperationException("The ruler selector has no matching UI item.");
            item.Select(); expand.Collapse(); await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
        }
        static IEnumerable<T> Descendants<T>(DependencyObject parent) where T : DependencyObject
        {
            for (int index = 0; index < VisualTreeHelper.GetChildrenCount(parent); index++)
            {
                var child = VisualTreeHelper.GetChild(parent, index);
                if (child is T matching) yield return matching;
                foreach (var nested in Descendants<T>(child)) yield return nested;
            }
        }
    }
}
