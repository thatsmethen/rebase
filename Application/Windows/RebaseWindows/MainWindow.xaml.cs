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
    private bool closeFinished, closing, updatingSourceList;
    private readonly Dictionary<string, Slider> mixerSliders = [];
    private string? mixerFocus;
    private bool mixerRefreshPending;
    private string? smokeAttachPath, smokeSourceExportPath;
    private int? darkCaptionResult;
    [DllImport("dwmapi.dll", ExactSpelling = true)]
    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    private static extern int DwmSetWindowAttribute(IntPtr window, uint attribute, ref int value, uint bytes);
    public MainWindow()
    {
        InitializeComponent(); DataContext = model;
        SourceInitialized += (_, _) =>
        {
            // Documented DWM opt-in keeps the native caption/resize behavior.
            // The window's visual-tree capture does not verify this OS frame.
            int enabled = 1;
            darkCaptionResult = DwmSetWindowAttribute(new WindowInteropHelper(this).Handle, 20, ref enabled, sizeof(int));
        };
        model.StateChanged += RefreshDocument;
        model.WaveformsChanged += () => Timeline.SetWaveforms(model.WaveformPeaks);
        model.PropertyChanged += ModelChanged;
        Timeline.ClipSelected += async id => await model.Command("selectClip", clipID: id);
        Timeline.ClipDragged += async (id, value, trim) => await model.Command(trim ? "trimClip" : "moveClip", clipID: id, value: value);
        Timeline.SeekRequested += async value => await model.SeekProject(value);
        Timeline.TrackSelected += async id => await model.Command("selectTrack", trackID: id);
        Timeline.TrackFlagChanged += async (id, solo) => await model.Command(solo ? "toggleSolo" : "toggleMute", trackID: id);
        timer.Tick += async (_, _) => await model.Poll(); timer.Start();
        Mixer.LostMouseCapture += (_, _) => { if (mixerRefreshPending && !Mixer.IsMouseCaptureWithin) RefreshMixer(); };
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
        if (e.PropertyName == nameof(model.Busy))
        {
            Timeline.IsEnabled = !model.Busy;
            CommandSurface.IsEnabled = !model.Busy;
            ProjectActions.IsEnabled = !model.Busy;
            MainMenu.IsEnabled = !model.Busy;
            ArrangementActions.IsEnabled = !model.Busy;
            EditSurface.IsEnabled = !model.Busy;
            Mixer.IsEnabled = !model.Busy;
            SourcePanel.IsEnabled = !model.Busy;
            UndoButton.IsEnabled = !model.Busy && model.State.CanUndo;
            RedoButton.IsEnabled = !model.Busy && model.State.CanRedo;
            if (!model.Busy && mixerFocus is not null && mixerSliders.TryGetValue(mixerFocus, out var restore))
            {
                mixerFocus = null;
                Dispatcher.BeginInvoke(() => restore.Focus(), DispatcherPriority.Input);
            }
        }
    }
    private void RefreshDocument()
    {
        if (Timeline is null) return;
        Timeline.SetProject(model.Project, model.State.Selection.ClipID, Zoom.Value);
        Timeline.SetWaveforms(model.WaveformPeaks);
        if (!model.IsSourceContext) Timeline.SetPosition(model.Position);
        UndoButton.IsEnabled = model.State.CanUndo && !model.Busy;
        RedoButton.IsEnabled = model.State.CanRedo && !model.Busy;
        TempoBox.Text = (model.Project?.Tempo ?? 120).ToString("0.###", CultureInfo.CurrentCulture);
        SelectionName.Text = model.SelectedClip?.Name ?? "None";
        ProjectName.Text = model.Project?.Name ?? "Untitled";
        InspectorTrack.Text = model.SelectedTrack?.Name ?? "No track selected";
        InspectorTrackInfo.Text = model.SelectedSourceEvent is not null ? "Retained source event" : model.SelectedTrack is null ? "Open a project to begin" : "Audio track";
        InspectorGain.Text = model.SelectedTrack is null ? "—" : $"{model.SelectedTrack.GainDB:0.0} dB";
        InspectorPan.Text = model.SelectedTrack is null ? "—" : PanText(model.SelectedTrack.Pan);
        SourceOffsetText.Text = $"{model.SelectedClip?.SourceOffset ?? 0:0.000} s";
        ClipInspector.Visibility = Visibility.Visible;
        ClipInspector.IsEnabled = model.SelectedClip is not null;
        MixerCount.Text = $"{model.Project?.Tracks.Length ?? 0} channels";
        MoveBox.Text = (model.SelectedClip?.Position ?? 0).ToString("0.######", CultureInfo.CurrentCulture);
        TrimBox.Text = ((model.SelectedClip?.Position ?? 0) + (model.SelectedClip?.Duration ?? 0)).ToString("0.######", CultureInfo.CurrentCulture);
        ProjectInfo.Text = model.Project is null ? "No project loaded" : $"{model.Project.Tracks.Length} tracks · {model.Project.SampleRate:0} Hz · {model.Project.Duration:0.##} seconds";
        var unresolved = model.Project?.Tracks.Sum(t => t.UnresolvedAudioEvents.Length) ?? 0;
        if (unresolved > 0) ProjectInfo.Text += $" · {unresolved} source events: project playback unavailable";
        updatingSourceList = true;
        try
        {
            var events = model.SourceEvents;
            SourcePanel.Visibility = events.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
            SourceEventsBox.ItemsSource = events;
            SourceEventsBox.SelectedItem = events.FirstOrDefault(item => item.Id == model.State.Selection.ClipID);
            SourceMediaInfo.Text = model.SelectedSourceEvent?.MediaStatus ?? "Select a retained event to attach matching PCM or audition its source.";
        }
        finally { updatingSourceList = false; }
        TransportContextName.Text = model.TransportContext;
        RefreshMixer();
    }
    private void RefreshMixer()
    {
        if (Mixer.IsMouseCaptureWithin) { mixerRefreshPending = true; return; }
        mixerRefreshPending = false;
        if (Keyboard.FocusedElement is Slider { Tag: string key } && mixerSliders.ContainsKey(key)) mixerFocus = key;
        Mixer.Children.Clear(); mixerSliders.Clear();
        var tracks = model.Project?.Tracks ?? [];
        for (int index = 0; index < tracks.Length; index++) AddChannel(tracks[index], index);
    }
    private void AddChannel(TrackView track, int index)
    {
        var accent = new SolidColorBrush(TimelineView.TrackColors[index % TimelineView.TrackColors.Length]);
        var panel = new Grid { Width = 84, Height = 209, Margin = new Thickness(3, 1, 3, 1) };
        panel.RowDefinitions.Add(new RowDefinition { Height = new GridLength(25) });
        panel.RowDefinitions.Add(new RowDefinition { Height = new GridLength(23) });
        panel.RowDefinitions.Add(new RowDefinition { Height = new GridLength(116) });
        panel.RowDefinitions.Add(new RowDefinition { Height = new GridLength(20) });
        panel.RowDefinitions.Add(new RowDefinition { Height = new GridLength(25) });
        var flags = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Center };
        var mute = new CheckBox { Content = "M", IsChecked = track.IsMuted, ToolTip = "Mute " + track.Name, MinWidth = 35, Margin = new Thickness(1), Padding = new Thickness(4, 2, 4, 2) };
        var solo = new CheckBox { Content = "S", IsChecked = track.IsSolo, ToolTip = "Solo " + track.Name, MinWidth = 35, Margin = new Thickness(1), Padding = new Thickness(4, 2, 4, 2) };
        AutomationProperties.SetName(mute, "Mute " + track.Name); AutomationProperties.SetName(solo, "Solo " + track.Name);
        mute.Click += async (_, _) => await model.Command("toggleMute", trackID: track.Id);
        solo.Click += async (_, _) => await model.Command("toggleSolo", trackID: track.Id);
        flags.Children.Add(mute); flags.Children.Add(solo); panel.Children.Add(flags);
        var pan = new Slider { Minimum = -1, Maximum = 1, Value = track.Pan, SmallChange = 0.01, LargeChange = 0.1, Height = 20, Margin = new Thickness(5, 0, 5, 0), ToolTip = PanText(track.Pan) };
        pan.Tag = track.Id + ":pan"; mixerSliders[(string)pan.Tag] = pan;
        Grid.SetRow(pan, 1); panel.Children.Add(pan); AutomationProperties.SetName(pan, track.Name + " pan");
        pan.ValueChanged += (_, _) => pan.ToolTip = PanText(pan.Value);
        pan.PreviewMouseLeftButtonUp += async (_, _) => await CommitMixerSlider(pan, "setPan", track.Id);
        pan.KeyUp += async (_, e) => { if (SliderEditKey(e.Key)) await CommitMixerSlider(pan, "setPan", track.Id); };
        var fader = new Grid { Background = new SolidColorBrush(Color.FromRgb(30, 33, 35)), Margin = new Thickness(5, 1, 5, 1) }; Grid.SetRow(fader, 2); panel.Children.Add(fader);
        var gain = new Slider { Minimum = -96, Maximum = 24, Value = track.GainDB, SmallChange = 0.5, LargeChange = 6,
            Orientation = Orientation.Vertical, Width = 28, Height = 110, HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(10, 2, 0, 2) };
        gain.Tag = track.Id + ":gain"; mixerSliders[(string)gain.Tag] = gain;
        AutomationProperties.SetName(gain, track.Name + " gain decibels"); fader.Children.Add(gain);
        fader.Children.Add(new TextBlock { Text = "+24\n\n0\n\n−48\n\n−96", FontSize = 8, Foreground = (Brush)FindResource("MutedBrush"), Margin = new Thickness(45, 2, 0, 0), IsHitTestVisible = false });
        var value = new TextBlock { Text = track.GainDB.ToString("0.00", CultureInfo.CurrentCulture), FontFamily = new FontFamily("Consolas"), HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center, FontSize = 10 };
        Grid.SetRow(value, 3); panel.Children.Add(value);
        gain.ValueChanged += (_, _) => value.Text = gain.Value.ToString("0.00", CultureInfo.CurrentCulture);
        gain.PreviewMouseLeftButtonUp += async (_, _) => await CommitMixerSlider(gain, "setGain", track.Id);
        gain.KeyUp += async (_, e) => { if (SliderEditKey(e.Key)) await CommitMixerSlider(gain, "setGain", track.Id); };
        var select = new Button { Content = new TextBlock { Text = track.Name, Foreground = Brushes.Black, FontSize = 10, TextTrimming = TextTrimming.CharacterEllipsis },
            HorizontalContentAlignment = HorizontalAlignment.Left, Padding = new Thickness(4, 2, 4, 2), Margin = new Thickness(0), MinHeight = 22,
            Background = accent, BorderBrush = Brushes.Transparent, Foreground = Brushes.Black };
        select.Click += async (_, _) => await model.Command("selectTrack", trackID: track.Id); Grid.SetRow(select, 4); panel.Children.Add(select);
        Mixer.Children.Add(new Border { Child = panel, Background = new SolidColorBrush(track.Id == model.State.Selection.TrackID ? Color.FromRgb(86, 91, 94) : Color.FromRgb(47, 51, 54)),
            Margin = new Thickness(0, 0, 2, 0), BorderThickness = new Thickness(1), BorderBrush = (Brush)FindResource("HairlineBrush") });
    }
    private async Task CommitMixerSlider(Slider control, string command, string trackID)
    {
        if (control.IsKeyboardFocusWithin) mixerFocus = (string)control.Tag;
        await model.Command(command, trackID: trackID, value: control.Value);
    }
    private static bool SliderEditKey(Key key) => key is Key.Left or Key.Right or Key.Up or Key.Down or Key.Home or Key.End or Key.PageUp or Key.PageDown;
    private static string PanText(double value) => Math.Abs(value) < 0.005 ? "Center" : (value < 0 ? "L " : "R ") + Math.Abs(value * 100).ToString("0", CultureInfo.CurrentCulture);
    private void TimelineViewportChanged(object sender, SizeChangedEventArgs e)
    {
        if (Timeline is not null) Timeline.SetViewport(Math.Max(0, e.NewSize.Width - 9));
    }
    private static double Number(TextBox box)
    {
        if (!double.TryParse(box.Text, NumberStyles.Float, CultureInfo.CurrentCulture, out var value) || !double.IsFinite(value))
            throw new InvalidOperationException("Enter a finite number.");
        return value;
    }
    private async Task Guard(Func<Task> action) { try { await action(); } catch (Exception error) { model.Report(error); } }
    private bool? DiscardDecision() => !model.State.Dirty ? false :
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
    private async Task<bool> SaveAs()
    {
        if (model.Project is null) return false;
        var dialog = new SaveFileDialog { Title = "Save as a new Rebase project folder", Filter = "Rebase project folder|*.rebaseproj", DefaultExt = ".rebaseproj", AddExtension = true, OverwritePrompt = false, FileName = model.Project.Name + ".rebaseproj" };
        if (dialog.ShowDialog(this) != true) return false;
        if (Directory.Exists(dialog.FileName) || File.Exists(dialog.FileName)) { model.Report(new IOException("Choose a new project name; Save As does not replace existing files or folders.")); return false; }
        await model.Save(dialog.FileName);
        return !model.State.Dirty && !model.State.NeedsSaveAs;
    }
    private async Task<bool> Save()
    {
        if (model.Project is null) return false;
        if (model.State.NeedsSaveAs || model.State.Path is null) return await SaveAs();
        await model.Save(); return !model.State.Dirty;
    }
    private async void SaveProject(object sender, RoutedEventArgs e) => await Guard(async () => { await Save(); });
    private async void SaveProjectAs(object sender, RoutedEventArgs e) => await Guard(async () => { await SaveAs(); });
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
    private async void KeyPressed(object sender, KeyEventArgs e)
    {
        if (model.Busy) return;
        if (e.OriginalSource is TextBox || e.OriginalSource is System.Windows.Controls.Primitives.TextBoxBase || e.OriginalSource is ComboBox) return;
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
        if (closing) return;
        closing = true;
        IsEnabled = false;
        try
        {
            // Wait for edits already dispatched before deciding whether there
            // are unsaved changes. Disabled input cannot enqueue another edit.
            await model.SuspendAndDrain();
            model.ResumeInput(); // Allows the explicit Save decision below.
            if (model.State.Dirty)
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
