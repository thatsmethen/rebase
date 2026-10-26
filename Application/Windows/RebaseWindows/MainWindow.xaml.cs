using Microsoft.Win32;
using System.ComponentModel;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Threading;

namespace Rebase.Windows;

public partial class MainWindow : Window
{
    private readonly StudioViewModel model = new();
    private readonly DispatcherTimer timer = new() { Interval = TimeSpan.FromMilliseconds(80) };
    private bool closeFinished, closing, updatingSourceList, updatingInspector, reviewingCPR;
    private readonly Dictionary<string, Slider> mixerSliders = [];
    private readonly Dictionary<string, TextBox> mixerValues = [];
    private string? mixerFocus;
    private FrameworkElement? inspectorFocus;
    private bool mixerRefreshPending;
    private string? smokeAttachPath, smokeSourceExportPath;
    private string? smokeCPRPath;
    private Func<string?>? smokeCPRDestination;
    private Func<MessageBoxResult>? smokeCPRDirtyDecision;
    private CPRReviewWindow? activeCPRReview;
    private int? darkCaptionResult;
    [DllImport("dwmapi.dll", ExactSpelling = true)]
    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    private static extern int DwmSetWindowAttribute(IntPtr window, uint attribute, ref int value, uint bytes);
    public MainWindow()
    {
        InitializeComponent(); DataContext = model; InitializeWorkspaceLayout();
        SourceInitialized += (_, _) =>
        {
            // Documented DWM opt-in keeps the native caption/resize behavior.
            // The window's visual-tree capture does not verify this OS frame.
            int enabled = 1;
            darkCaptionResult = DwmSetWindowAttribute(new WindowInteropHelper(this).Handle, 20, ref enabled, sizeof(int));
        };
        model.StateChanged += RefreshDocument;
        model.WaveformsChanged += () => Timeline.SetWaveforms(model.WaveformPeaks);
        model.RulerChanged += RefreshRuler;
        model.PropertyChanged += ModelChanged;
        Timeline.ClipSelected += async id => await model.Command("selectClip", clipID: id);
        Timeline.ClipDragged += async (id, value, trim) => await model.Command(trim ? "trimClip" : "moveClip", clipID: id, value: value);
        Timeline.SeekRequested += async value => await model.SeekProject(value);
        Timeline.TrackSelected += async id => await model.Command("selectTrack", trackID: id);
        Timeline.TrackFlagChanged += async (id, solo) => await model.Command(solo ? "toggleSolo" : "toggleMute", trackID: id);
        TimelineScroll.ScrollChanged += TimelineViewportChanged;
        timer.Tick += async (_, _) => await model.Poll(); timer.Start();
        Mixer.LostMouseCapture += (_, _) => FinishMixerCapture();
        SelectedChannel.LostMouseCapture += (_, _) => FinishMixerCapture();
        RefreshDocument();
    }
    private void ModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(model.Position))
        {
            if (!model.IsSourceContext) Timeline.SetPosition(model.Position);
            Timecode.Text = TimeSpan.FromSeconds(Math.Max(0, model.Position)).ToString(@"hh\:mm\:ss\.fff", CultureInfo.InvariantCulture);
            if (!PositionBox.IsKeyboardFocused) PositionBox.Text = model.Position.ToString("0.000", CultureInfo.CurrentCulture);
        }
        if (e.PropertyName == nameof(model.TransportContext)) TransportContextName.Text = model.TransportContext;
        if (e.PropertyName is nameof(model.Busy) or nameof(model.SourceStreamPreparing))
        {
            CommandSurface.IsEnabled = !model.Busy || model.SourceStreamPreparing;
            TransportStopButton.IsEnabled = !model.Busy || model.SourceStreamPreparing;
            TransportPauseButton.IsEnabled = TransportPlayButton.IsEnabled = TransportTempoControls.IsEnabled = TransportPositionControls.IsEnabled = !model.Busy;
        }
        if (e.PropertyName == nameof(model.Busy))
        {
            Timeline.IsEnabled = !model.Busy;
            ProjectActions.IsEnabled = !model.Busy;
            MainMenu.IsEnabled = !model.Busy;
            ArrangementActions.IsEnabled = !model.Busy;
            EditSurface.IsEnabled = !model.Busy;
            Mixer.IsEnabled = !model.Busy;
            ChannelSurface.IsEnabled = !model.Busy;
            SourcePanel.IsEnabled = !model.Busy;
            RefreshEditingAvailability();
            InspectorTrackControls.IsEnabled = !model.Busy && model.SelectedTrack is not null;
            AutomationMenu.IsEnabled = InspectorTrackControls.IsEnabled;
            UndoButton.IsEnabled = !model.Busy && model.State.CanUndo;
            RedoButton.IsEnabled = !model.Busy && model.State.CanRedo;
            RestoreMixerFocus();
            if (!model.Busy && inspectorFocus is { } inspectorRestore)
            {
                inspectorFocus = null;
                Dispatcher.BeginInvoke(() => { if (inspectorRestore.IsVisible && inspectorRestore.IsEnabled) inspectorRestore.Focus(); }, DispatcherPriority.Input);
            }
        }
    }
    private void RefreshDocument()
    {
        if (Timeline is null) return;
        Timeline.SetProject(model.Project, model.State.Selection.ClipID, model.State.Selection.TrackID, Zoom.Value);
        Timeline.SetWaveforms(model.WaveformPeaks);
        model.SetRulerViewport(Zoom.Value, Math.Max(24, model.Project?.Duration ?? 24));
        RefreshRuler();
        if (!model.IsSourceContext) Timeline.SetPosition(model.Position);
        UndoButton.IsEnabled = model.State.CanUndo && !model.Busy;
        RedoButton.IsEnabled = model.State.CanRedo && !model.Busy;
        TempoBox.Text = (model.Project?.Tempo ?? 120).ToString("0.###", CultureInfo.CurrentCulture);
        SelectionName.Text = model.SelectedClip?.Name ?? model.SelectedSourceEvent?.Name ?? "No event selected";
        SelectionName.ToolTip = SelectionName.Text;
        SelectionKind.Text = model.SelectedSourceEvent is not null ? "Retained source event" : model.SelectedClip is not null ? "Selected event" : "Event information";
        ProjectName.Text = model.Project?.Name ?? "Untitled";
        ProjectName.ToolTip = ProjectName.Text;
        InspectorTrack.Text = model.SelectedTrack?.Name ?? "No track selected";
        ChannelTrack.Text = model.SelectedTrack?.Name ?? "No selection";
        var selectedIndex = Array.FindIndex(model.Project?.Tracks ?? [], track => track.Id == model.State.Selection.TrackID);
        var selectedBrush = new SolidColorBrush(selectedIndex < 0 ? Color.FromRgb(69, 74, 78) : TimelineView.TrackColors[selectedIndex % TimelineView.TrackColors.Length]);
        ChannelTrackPlate.Background = InspectorTrackPlate.Background = selectedBrush;
        InspectorTrackInfo.Text = model.SelectedSourceEvent is not null ? "Retained source event" : model.SelectedTrack is null ? "Open a project to begin" : "Audio track";
        InspectorGain.Text = model.SelectedTrack is null ? "—" : $"{model.SelectedTrack.GainDB:0.0} dB";
        InspectorPan.Text = model.SelectedTrack is null ? "—" : PanText(model.SelectedTrack.Pan);
        InspectorTrackControls.IsEnabled = model.SelectedTrack is not null && !model.Busy;
        AutomationMenu.IsEnabled = InspectorTrackControls.IsEnabled;
        updatingInspector = true;
        try
        {
            InspectorGainSlider.Value = model.SelectedTrack?.GainDB ?? 0;
            InspectorPanSlider.Value = model.SelectedTrack?.Pan ?? 0;
            InspectorMute.IsChecked = model.SelectedTrack?.IsMuted ?? false;
            InspectorSolo.IsChecked = model.SelectedTrack?.IsSolo ?? false;
        }
        finally { updatingInspector = false; }
        SourceOffsetText.Text = model.SelectedClip is { } offsetClip ? $"{offsetClip.SourceOffset:0.000} s" : "—";
        SourceOffsetText.ToolTip = model.SelectedClip is null ? "Ordinary event timing is unavailable for this selection." : SourceOffsetText.Text;
        ClipInspector.Visibility = Visibility.Visible;
        ClipInspector.IsEnabled = model.SelectedClip is not null;
        MixerCount.Text = $"{model.Project?.Tracks.Length ?? 0} channels";
        MoveBox.Text = model.SelectedClip?.Position.ToString("0.######", CultureInfo.CurrentCulture) ?? "—";
        TrimBox.Text = model.SelectedClip is { } endClip ? (endClip.Position + endClip.Duration).ToString("0.######", CultureInfo.CurrentCulture) : "—";
        ProjectInfo.Text = model.Project is null ? "No project loaded" : $"{model.Project.Tracks.Length} tracks · {model.Project.SampleRate:0} Hz · {model.Project.Duration:0.##} seconds";
        var unresolved = model.Project?.Tracks.Sum(t => t.UnresolvedAudioEvents.Length) ?? 0;
        ProjectInfo.ToolTip = ProjectInfo.Text;
        ProjectLimit.Visibility = unresolved > 0 ? Visibility.Visible : Visibility.Collapsed;
        ProjectLimit.ToolTip = $"{unresolved} retained source events. Project playback is unavailable; isolated source audition is available in the Inspector.";
        updatingSourceList = true;
        try
        {
            var events = model.SourceEvents;
            SourceSection.Visibility = events.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
            SourceEventsBox.ItemsSource = events;
            SourceEventsBox.SelectedItem = events.FirstOrDefault(item => item.Id == model.State.Selection.ClipID);
            SourceMediaInfo.Text = model.SelectedSourceEvent?.MediaStatus ?? "Select a retained event to attach matching PCM or audition its source.";
        }
        finally { updatingSourceList = false; }
        RefreshEditingAvailability();
        TransportContextName.Text = model.TransportContext;
        RefreshMixer();
    }
    private void FinishMixerCapture()
    {
        if (mixerRefreshPending && !Mixer.IsMouseCaptureWithin && !SelectedChannel.IsMouseCaptureWithin) RefreshMixer();
    }
    private void RefreshMixer()
    {
        if (Mixer.IsMouseCaptureWithin || SelectedChannel.IsMouseCaptureWithin) { mixerRefreshPending = true; return; }
        mixerRefreshPending = false;
        if (Keyboard.FocusedElement is Control { Tag: string key } && (mixerSliders.ContainsKey(key) || mixerValues.ContainsKey(key))) mixerFocus = key;
        Mixer.Children.Clear(); SelectedChannel.Content = null; mixerSliders.Clear(); mixerValues.Clear();
        var tracks = model.Project?.Tracks ?? [];
        for (int index = 0; index < tracks.Length; index++)
        {
            Mixer.Children.Add(CreateChannel(tracks[index], index, false));
            if (tracks[index].Id == model.State.Selection.TrackID) SelectedChannel.Content = CreateChannel(tracks[index], index, true);
        }
    }
    private Border CreateChannel(TrackView track, int index, bool selectedStrip)
    {
        var accent = new SolidColorBrush(TimelineView.TrackColors[index % TimelineView.TrackColors.Length]);
        var prefix = selectedStrip ? "channel:" : "";
        var faderHeight = selectedStrip ? 200 : mixerFaderHeight;
        var panel = new Grid { Width = selectedStrip ? 84 : 72, Height = faderHeight + 99, Margin = new Thickness(3, 1, 3, 1) };
        foreach (var height in new double[] { 25, 23, faderHeight + 6, 20, 25 }) panel.RowDefinitions.Add(new RowDefinition { Height = new GridLength(height) });
        var flags = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Center };
        var mute = new CheckBox { Content = "M", IsChecked = track.IsMuted, ToolTip = "Mute " + track.Name, MinWidth = selectedStrip ? 35 : 29, Margin = new Thickness(1), Padding = new Thickness(4, 2, 4, 2) };
        var solo = new CheckBox { Content = "S", IsChecked = track.IsSolo, ToolTip = "Solo " + track.Name, MinWidth = selectedStrip ? 35 : 29, Margin = new Thickness(1), Padding = new Thickness(4, 2, 4, 2) };
        AutomationProperties.SetName(mute, "Mute " + track.Name); AutomationProperties.SetName(solo, "Solo " + track.Name);
        // Subscribe after loading state, so a refresh never sends an edit.
        RoutedEventHandler muteChanged = async (_, _) => await model.Command("toggleMute", trackID: track.Id);
        RoutedEventHandler soloChanged = async (_, _) => await model.Command("toggleSolo", trackID: track.Id);
        mute.Checked += muteChanged; mute.Unchecked += muteChanged; solo.Checked += soloChanged; solo.Unchecked += soloChanged;
        flags.Children.Add(mute); flags.Children.Add(solo); panel.Children.Add(flags);
        var pan = new CommitSlider { Style = (Style)FindResource(typeof(Slider)), Minimum = -1, Maximum = 1, Value = track.Pan, SmallChange = 0.01, LargeChange = 0.1, Height = 20, Margin = new Thickness(5, 0, 5, 0), ToolTip = PanText(track.Pan) };
        pan.Tag = prefix + track.Id + ":pan"; mixerSliders[(string)pan.Tag] = pan;
        Grid.SetRow(pan, 1); panel.Children.Add(pan); AutomationProperties.SetName(pan, track.Name + " pan");
        pan.ValueChanged += (_, _) => pan.ToolTip = PanText(pan.Value);
        pan.ValueCommitted += async (_, _) => await CommitMixerSlider(pan, "setPan", track.Id);
        var fader = new Grid { Background = new SolidColorBrush(Color.FromRgb(30, 33, 35)), Margin = new Thickness(5, 1, 5, 1) }; Grid.SetRow(fader, 2); panel.Children.Add(fader);
        var gain = new CommitSlider { Style = (Style)FindResource(typeof(Slider)), Minimum = -96, Maximum = 24, Value = track.GainDB, SmallChange = 0.5, LargeChange = 6,
            Orientation = Orientation.Vertical, Width = 28, Height = faderHeight, HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(4, 2, 0, 2) };
        gain.Tag = prefix + track.Id + ":gain"; mixerSliders[(string)gain.Tag] = gain;
        AutomationProperties.SetName(gain, track.Name + " gain decibels"); fader.Children.Add(gain);
        var scale = new FaderScale(gain) { Width = selectedStrip ? 35 : 25, Height = faderHeight, Margin = new Thickness(selectedStrip ? 36 : 34, 2, 0, 2), HorizontalAlignment = HorizontalAlignment.Left, IsHitTestVisible = false };
        fader.Children.Add(scale);
        var value = new TextBox { Text = track.GainDB.ToString("0.00", CultureInfo.CurrentCulture), FontFamily = new FontFamily("Consolas"), TextAlignment = TextAlignment.Center,
            MinHeight = 18, Height = 18, Margin = new Thickness(4, 1, 4, 1), Padding = new Thickness(2, 0, 2, 0), FontSize = 10, Tag = prefix + track.Id + ":gainValue", ToolTip = "Volume in dB. Enter to apply; Escape to cancel." };
        AutomationProperties.SetName(value, track.Name + " volume value decibels"); mixerValues[(string)value.Tag] = value;
        Grid.SetRow(value, 3); panel.Children.Add(value);
        gain.ValueChanged += (_, _) => value.Text = gain.Value.ToString("0.00", CultureInfo.CurrentCulture);
        gain.ValueCommitted += async (_, _) => await CommitMixerSlider(gain, "setGain", track.Id);
        value.PreviewKeyDown += async (_, e) =>
        {
            if (e.Key == Key.Escape) { value.Text = gain.Value.ToString("0.00", CultureInfo.CurrentCulture); value.SelectAll(); e.Handled = true; }
            if (e.Key != Key.Enter) return;
            e.Handled = true;
            if (!double.TryParse(value.Text, NumberStyles.Float, CultureInfo.CurrentCulture, out var number) || !double.IsFinite(number) || number < gain.Minimum || number > gain.Maximum)
            {
                value.Text = gain.Value.ToString("0.00", CultureInfo.CurrentCulture); value.SelectAll();
                model.Report(new InvalidOperationException("Volume must be a finite value from -96 to +24 dB.")); return;
            }
            mixerFocus = (string)value.Tag;
            await model.Command("setGain", trackID: track.Id, value: number);
        };
        value.LostKeyboardFocus += (_, _) => value.Text = gain.Value.ToString("0.00", CultureInfo.CurrentCulture);
        var select = new Button { Content = new TextBlock { Text = track.Name, Foreground = Brushes.Black, FontSize = 10, TextTrimming = TextTrimming.CharacterEllipsis },
            Style = (Style)FindResource("AccentSurfaceButton"), HorizontalContentAlignment = HorizontalAlignment.Left, Padding = new Thickness(4, 2, 4, 2), Margin = new Thickness(0), MinHeight = 22,
            Background = accent, BorderBrush = Brushes.Transparent, Foreground = Brushes.Black };
        select.Click += async (_, _) => await model.Command("selectTrack", trackID: track.Id); Grid.SetRow(select, 4); panel.Children.Add(select);
        return new Border { Child = panel, VerticalAlignment = VerticalAlignment.Bottom, Background = new SolidColorBrush(track.Id == model.State.Selection.TrackID ? Color.FromRgb(86, 91, 94) : Color.FromRgb(47, 51, 54)),
            Margin = new Thickness(0, 0, 2, 0), BorderThickness = new Thickness(1), BorderBrush = (Brush)FindResource("HairlineBrush") };
    }
    private async Task CommitMixerSlider(Slider control, string command, string trackID)
    {
        if (control.IsKeyboardFocusWithin) mixerFocus = (string)control.Tag;
        await model.Command(command, trackID: trackID, value: control.Value);
    }
    private async Task CommitInspector(FrameworkElement control, string command, double? value = null)
    {
        if (model.SelectedTrack is not { } track || model.Busy) return;
        if (control.IsKeyboardFocusWithin) inspectorFocus = control;
        await model.Command(command, trackID: track.Id, value: value);
    }
    private async void InspectorGainCommitted(object? sender, EventArgs e) => await CommitInspector(InspectorGainSlider, "setGain", InspectorGainSlider.Value);
    private async void InspectorPanCommitted(object? sender, EventArgs e) => await CommitInspector(InspectorPanSlider, "setPan", InspectorPanSlider.Value);
    private async void InspectorMuteChanged(object sender, RoutedEventArgs e) { if (!updatingInspector) await CommitInspector(InspectorMute, "toggleMute"); }
    private async void InspectorSoloChanged(object sender, RoutedEventArgs e) { if (!updatingInspector) await CommitInspector(InspectorSolo, "toggleSolo"); }
    private void InspectorGainPreview(object sender, RoutedPropertyChangedEventArgs<double> e) { if (InspectorGain is not null) InspectorGain.Text = $"{e.NewValue:0.0} dB"; }
    private void InspectorPanPreview(object sender, RoutedPropertyChangedEventArgs<double> e) { if (InspectorPan is not null) InspectorPan.Text = PanText(e.NewValue); }
    private static string PanText(double value) => Math.Abs(value) < 0.005 ? "Center" : (value < 0 ? "L " : "R ") + Math.Abs(value * 100).ToString("0", CultureInfo.CurrentCulture);
    private void TimelineViewportChanged(object sender, ScrollChangedEventArgs e)
    {
        if (!ReferenceEquals(e.OriginalSource, TimelineScroll)) return;
        Timeline.SetHorizontalOffset(TimelineScroll.HorizontalOffset);
        // ScrollChanged reports the measured content viewport after scrollbar
        // allocation. The outer control size cannot predict that allocation.
        if (double.IsFinite(e.ViewportWidth) && double.IsFinite(e.ViewportHeight) && e.ViewportWidth > 0 && e.ViewportHeight > 0)
            Timeline.SetViewport(e.ViewportWidth, e.ViewportHeight);
    }
    private static double Number(TextBox box)
    {
        if (!double.TryParse(box.Text, NumberStyles.Float, CultureInfo.CurrentCulture, out var value) || !double.IsFinite(value))
            throw new InvalidOperationException("Enter a finite number.");
        return value;
    }
    private async Task Guard(Func<Task> action) { try { await action(); } catch (Exception error) { model.Report(error); } }
    private bool? DiscardDecision() => !model.NeedsSaveDecision ? false :
        MessageBox.Show(this, "Discard unsaved changes and open another project?", "Unsaved changes", MessageBoxButton.YesNo, MessageBoxImage.Question) == MessageBoxResult.Yes ? true : null;
    private async void OpenExample(object sender, RoutedEventArgs e)
    {
        var discard = DiscardDecision();
        if (discard is null) return;
        var path = Path.Combine(AppContext.BaseDirectory, "Examples", "Rebase Preview.rebaseproj", "Project.json");
        if (!File.Exists(path)) { model.Report(new FileNotFoundException("The included example is missing from this release folder.")); return; }
        await model.Open(path, asCopy: true, discardChanges: discard.Value);
    }
    private async void OpenProject(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog { Title = "Open Project.json inside a Rebase project folder", Filter = "Rebase project manifest|Project.json", CheckFileExists = true };
        if (dialog.ShowDialog(this) == true)
        {
            var discard = DiscardDecision();
            if (discard is not null) await model.Open(dialog.FileName, asCopy: false, discardChanges: discard.Value);
        }
    }
    private async Task<bool> SaveAs(Window? owner = null)
    {
        if (model.Project is null) return false;
        var dialog = new SaveFileDialog { Title = "Save as a new Rebase project folder", Filter = "Rebase project folder|*.rebaseproj", DefaultExt = ".rebaseproj", AddExtension = true, OverwritePrompt = false, FileName = model.Project.Name + ".rebaseproj" };
        if (dialog.ShowDialog(owner ?? this) != true) return false;
        if (Directory.Exists(dialog.FileName) || File.Exists(dialog.FileName)) { model.Report(new IOException("Choose a new project name; Save As does not replace existing files or folders.")); return false; }
        return await model.Save(dialog.FileName) && !model.State.Dirty && !model.State.NeedsSaveAs;
    }
    private async Task<bool> Save(Window? owner = null)
    {
        if (model.Project is null) return false;
        if (model.State.NeedsSaveAs || model.State.Path is null) return await SaveAs(owner);
        return await model.Save() && !model.State.Dirty;
    }
    private async void SaveProject(object sender, RoutedEventArgs e) => await Guard(async () => { await Save(); });
    private async void SaveProjectAs(object sender, RoutedEventArgs e) => await Guard(async () => { await SaveAs(); });
    private async void ImportCPRProject(object sender, RoutedEventArgs e)
    {
        var path = smokeCPRPath;
        if (path is null)
        {
            var dialog = new OpenFileDialog { Title = "Review a CPR project before importing supported data", Filter = "CPR project|*.cpr", CheckFileExists = true };
            if (dialog.ShowDialog(this) != true) return;
            path = dialog.FileName;
        }
        await ShowCPRReview(path);
    }
    private async void ShowCPRImportReport(object sender, RoutedEventArgs e) => await ShowCPRReview(null);
    private async Task ShowCPRReview(string? source)
    {
        if (reviewingCPR || closing) return;
        reviewingCPR = true;
        IsEnabled = false;
        try
        {
            await model.SuspendAndDrain(); model.ResumeInput();
            var review = source is null ? await model.ImportReport() : await model.InspectCPR(source);
            if (review is null) return;
            activeCPRReview = new CPRReviewWindow(model, review, ImportReviewedCPR) { Owner = this };
            activeCPRReview.Show();
            await activeCPRReview.Completion;
        }
        catch (Exception error) { model.Report(error); }
        finally { activeCPRReview = null; reviewingCPR = false; model.ResumeInput(); IsEnabled = true; Activate(); }
    }
    private async Task<bool> ImportReviewedCPR(CPRReviewSnapshot review)
    {
        // The owner remains disabled. Drain any prior work before the dirty
        // decision; Save may change the revision but retains this review token.
        await model.SuspendAndDrain(); model.ResumeInput();
        var discard = false;
        if (model.NeedsSaveDecision)
        {
            var answer = smokeCPRDirtyDecision?.Invoke() ?? MessageBox.Show((Window?)activeCPRReview ?? this,
                "Save changes to the current project before importing?\nYes: Save · No: Discard · Cancel: Keep reviewing",
                "Unsaved changes", MessageBoxButton.YesNoCancel, MessageBoxImage.Question);
            if (answer == MessageBoxResult.Cancel) { model.Report(new InvalidOperationException("Import canceled; the current project and review are unchanged.")); return false; }
            if (answer == MessageBoxResult.Yes && !await Save(activeCPRReview)) return false;
            discard = answer == MessageBoxResult.No;
        }
        string? destination;
        if (smokeCPRDestination is not null) destination = smokeCPRDestination();
        else
        {
            var dialog = new SaveFileDialog { Title = "Import supported data into a new Rebase project folder", Filter = "Rebase project folder|*.rebaseproj",
                DefaultExt = ".rebaseproj", AddExtension = true, OverwritePrompt = false, FileName = Path.GetFileNameWithoutExtension(review.SourceName) + ".rebaseproj" };
            destination = dialog.ShowDialog((Window?)activeCPRReview ?? this) == true ? dialog.FileName : null;
        }
        if (destination is null) { model.Report(new InvalidOperationException("No destination selected. The review remains open; no CPR project was imported.")); return false; }
        if (Directory.Exists(destination) || File.Exists(destination)) { model.Report(new IOException("Choose a new project name; importing does not replace existing files or folders.")); return false; }
        return await model.ImportCPR(review, destination, discard);
    }
    private async void ExportWav(object sender, RoutedEventArgs e)
    {
        if (model.Project is null) return;
        var dialog = new SaveFileDialog { Title = "Export a new WAV file outside the project", Filter = "Wave audio|*.wav", DefaultExt = ".wav", AddExtension = true, OverwritePrompt = false };
        if (dialog.ShowDialog(this) == true) await model.RenderTo(dialog.FileName);
    }
    private async void Undo(object sender, RoutedEventArgs e) => await model.Command("undo");
    private async void Redo(object sender, RoutedEventArgs e) => await model.Command("redo");
    private async void Play(object sender, RoutedEventArgs e) => await model.PlayProject();
    private async void Pause(object sender, RoutedEventArgs e) => await model.Pause();
    private async void Stop(object sender, RoutedEventArgs e) => await model.Stop();
    private async void SourceSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!updatingSourceList && SourceEventsBox.SelectedItem is SourceEventView item && item.Id != model.State.Selection.ClipID)
            await model.Command("selectClip", clipID: item.Id);
    }
    private async void AttachSourcePCM(object sender, RoutedEventArgs e)
    {
        if (model.SelectedSourceEvent is null) { model.Report(new InvalidOperationException("Select a retained source event first.")); return; }
        if (smokeAttachPath is not null) { await model.AttachSourceMedia(smokeAttachPath); return; }
        var dialog = new OpenFileDialog { Title = "Attach matching PCM24 WAV to the selected source event", Filter = "PCM WAV audio|*.wav;*.wave", CheckFileExists = true };
        if (dialog.ShowDialog(this) == true) await model.AttachSourceMedia(dialog.FileName);
    }
    private async void AuditionSource(object sender, RoutedEventArgs e) => await model.AuditionSource();
    private async void ExportSource(object sender, RoutedEventArgs e)
    {
        if (model.SelectedSourceEvent is null) { model.Report(new InvalidOperationException("Select a retained source event first.")); return; }
        if (smokeSourceExportPath is not null) { await model.RenderSourceTo(smokeSourceExportPath); return; }
        var dialog = new SaveFileDialog { Title = "Export checked source event to a new WAV outside the project", Filter = "Wave audio|*.wav", DefaultExt = ".wav", AddExtension = true, OverwritePrompt = false };
        if (dialog.ShowDialog(this) == true) await model.RenderSourceTo(dialog.FileName);
    }
    private async void Seek(object sender, RoutedEventArgs e) => await Guard(() => model.Seek(Number(PositionBox)));
    private async void SetTempo(object sender, RoutedEventArgs e) => await Guard(() => model.Command("setTempo", value: Number(TempoBox)));
    private async void MoveClip(object sender, RoutedEventArgs e) { if (model.SelectedClip is not null) await Guard(() => model.Command("moveClip", clipID: model.SelectedClip.Id, value: Number(MoveBox))); }
    private async void TrimClip(object sender, RoutedEventArgs e) { if (model.SelectedClip is not null) await Guard(() => model.Command("trimClip", clipID: model.SelectedClip.Id, value: Number(TrimBox))); }
    private async void SplitClip(object sender, RoutedEventArgs e) { if (model.SelectedClip is not null) await model.Command("splitClip", clipID: model.SelectedClip.Id, value: model.Position); }
    private async void DeleteClip(object sender, RoutedEventArgs e) { if (model.SelectedClip is not null) await model.Command("deleteEvent", clipID: model.SelectedClip.Id); }
    private void SnapChanged(object sender, SelectionChangedEventArgs e) { if (SnapBox?.SelectedItem is ComboBoxItem item) model.Snap = (string)item.Tag; }
    private void ZoomChanged(object sender, RoutedPropertyChangedEventArgs<double> e) { if (Timeline is not null) RefreshDocument(); }
    private void RulerModeChanged(object sender, SelectionChangedEventArgs e) { if (Timeline is not null) RefreshRuler(); }
    private void RefreshRuler() => Timeline.SetRuler(model.Ruler, RulerModeBox?.SelectedIndex != 1, model.RulerError);
    private async void KeyPressed(object sender, KeyEventArgs e)
    {
        if (model.Busy)
        {
            if (e.Key == Key.Escape && model.SourceStreamPreparing) { e.Handled = true; await model.Stop(); }
            return;
        }
        if (e.OriginalSource is TextBox || e.OriginalSource is System.Windows.Controls.Primitives.TextBoxBase || e.OriginalSource is ComboBox) return;
        if (e.Key == Key.Space && Keyboard.FocusedElement is System.Windows.Controls.Primitives.ButtonBase) return;
        if (Keyboard.Modifiers == ModifierKeys.Control && e.Key == Key.S) { e.Handled = true; await Guard(async () => { await Save(); }); }
        else if (Keyboard.Modifiers == ModifierKeys.Control && e.Key == Key.Z) { e.Handled = true; await model.Command("undo"); }
        else if (Keyboard.Modifiers == ModifierKeys.Control && e.Key == Key.Y) { e.Handled = true; await model.Command("redo"); }
        else if (e.Key == Key.Space) { e.Handled = true; if (model.IsPlaying) await model.Pause(); else await model.Play(); }
        else if (e.Key == Key.Delete && model.SelectedClip is not null) { e.Handled = true; await model.Command("deleteEvent", clipID: model.SelectedClip.Id); }
    }
    private async void ClosingWindow(object? sender, CancelEventArgs e)
    {
        if (closeFinished) return;
        e.Cancel = true;
        if (reviewingCPR) { activeCPRReview?.Activate(); return; }
        if (openingAutomation) { activeAutomationEditor?.Activate(); return; }
        if (openingSourceAudio) { activeSourceAudio?.Activate(); return; }
        if (closing) return;
        closing = true;
        IsEnabled = false;
        try
        {
            // Wait for edits already dispatched before deciding whether there
            // are unsaved changes. Disabled input cannot enqueue another edit.
            await model.SuspendAndDrain();
            model.ResumeInput(); // Allows the explicit Save decision below.
            if (model.NeedsSaveDecision)
            {
                var answer = MessageBox.Show(this, "Save changes before closing?", "Unsaved changes", MessageBoxButton.YesNoCancel, MessageBoxImage.Question);
                if (answer == MessageBoxResult.Cancel || (answer == MessageBoxResult.Yes && !await Save())) { closing = false; IsEnabled = true; return; }
            }
            timer.Stop();
            await model.DisposeAsync(); closeFinished = true; Close();
        }
        catch (Exception error) { model.Report(error); model.ResumeInput(); closing = false; IsEnabled = true; }
    }
}
