using System.Diagnostics;
using System.Text.Json;
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
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(sourceProject is null ? 120 : 180));
        string stage = "window-layout", endpoint = "not-probed", error = "";
        object[] processModules = [], helperModules = [];
        object? timelineScrollReceipt = null;
        object? windowBounds = null;
        object? musicalRulerReceipt = null;
        var faderScaleReceipt = new List<object>();
        object? channelAlignment = null;
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
            , timeline_scroll = timelineScrollReceipt, timeline_scroll_screenshot = "native-timeline-scroll-visual.png"
            , window_bounds = windowBounds
            , musical_ruler = musicalRulerReceipt, fader_scale = faderScaleReceipt, channel_alignment = channelAlignment
        };
        try { await File.WriteAllTextAsync(artifact, JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true })); }
        catch (IOException) { return 2; }
        return exit;

        async Task Scenario()
        {
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            Assert(IsVisible && ActualWidth >= 1020 && ActualHeight >= 700, "visible-window-layout");
            var snapOrigin = SnapBox.TransformToAncestor(ProjectActions).Transform(new Point());
            Assert(snapOrigin.Y >= 0 && snapOrigin.Y + SnapBox.ActualHeight <= ProjectActions.ActualHeight, "snap-control-fits-toolbar");
            stage = "open-example-button"; await Invoke(ExampleButton);
            await Until(() => model.Project?.Tracks.Length == 4 && !model.Busy, stage);
            Assert(model.State.NeedsSaveAs && model.State.Path is null, "bundled-example-is-copy");
            var first = model.Project!.Tracks.SelectMany(t => t.Clips).First();
            stage = "select-clip-button";
            await Invoke(Timeline.Children.OfType<Button>().First());
            await Until(() => model.State.Selection.ClipID == first.Id && !model.Busy, stage);
            Assert(model.SelectedClip is not null, "clip-selection");
            var originalTrack = model.SelectedTrack!;
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            Assert(ChannelTrack.Text == originalTrack.Name && InspectorTrack.Text == originalTrack.Name &&
                SelectedChannel.Content is not null &&
                Timeline.TrackHeaders.Single(header => Equals(header.Tag, originalTrack.Id)) is Grid { Background: SolidColorBrush selectedHeader } &&
                selectedHeader.Color == Color.FromRgb(87, 92, 95), "selection-synchronized-across-panes");

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
            var eventBefore = Origin(eventButton);
            var offsetBefore = TimelineScroll.HorizontalOffset;
            scroll.SetScrollPercent(20, System.Windows.Automation.ScrollPatternIdentifiers.NoScroll);
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            var headersAfter = Timeline.TrackHeaders.Select(Origin).ToArray();
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
                event_before = new { x = eventBefore.X, y = eventBefore.Y }, event_after = new { x = eventAfter.X, y = eventAfter.Y }
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
            checks.Add("window-visual-artifact-written"); stage = "completed";
        }
        Point Origin(FrameworkElement element) => element.TransformToAncestor(this).Transform(new Point());
        CheckBox MixerFlag(string name) => Descendants<CheckBox>(Mixer).Single(control => System.Windows.Automation.AutomationProperties.GetName(control) == name);
        async Task Capture(string filename)
        {
            await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            var client = Content as FrameworkElement ?? throw new InvalidOperationException("The window has no client visual.");
            var dpi = VisualTreeHelper.GetDpi(this);
            windowBounds = new { outer_width = ActualWidth, outer_height = ActualHeight, client_width = client.ActualWidth, client_height = client.ActualHeight, dpi_x = dpi.PixelsPerInchX, dpi_y = dpi.PixelsPerInchY };
            var image = new RenderTargetBitmap((int)Math.Ceiling(client.ActualWidth), (int)Math.Ceiling(client.ActualHeight), 96, 96, PixelFormats.Pbgra32);
            image.Render(client);
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
