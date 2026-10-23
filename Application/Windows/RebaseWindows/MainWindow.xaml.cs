using Microsoft.Win32;
using System.ComponentModel;
using System.Globalization;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Threading;

namespace Rebase.Windows;

public partial class MainWindow : Window
{
    private readonly StudioViewModel model = new();
    private readonly DispatcherTimer timer = new() { Interval = TimeSpan.FromMilliseconds(80) };
    private bool closeFinished, closing;
    public MainWindow()
    {
        InitializeComponent(); DataContext = model;
        model.StateChanged += RefreshDocument;
        model.PropertyChanged += ModelChanged;
        Timeline.ClipSelected += async id => await model.Command("selectClip", clipID: id);
        Timeline.ClipDragged += async (id, value, trim) => await model.Command(trim ? "trimClip" : "moveClip", clipID: id, value: value);
        Timeline.SeekRequested += async value => await model.Seek(value);
        timer.Tick += async (_, _) => await model.Poll(); timer.Start();
        RefreshDocument();
    }
    private void ModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(model.Position))
        {
            Timeline.SetPosition(model.Position);
            if (!PositionBox.IsKeyboardFocused) PositionBox.Text = model.Position.ToString("0.000", CultureInfo.CurrentCulture);
        }
        if (e.PropertyName == nameof(model.Busy))
        {
            Timeline.IsEnabled = !model.Busy;
            CommandSurface.IsEnabled = !model.Busy;
            EditSurface.IsEnabled = !model.Busy;
            Mixer.IsEnabled = !model.Busy;
            UndoButton.IsEnabled = !model.Busy && model.State.CanUndo;
            RedoButton.IsEnabled = !model.Busy && model.State.CanRedo;
        }
    }
    private void RefreshDocument()
    {
        if (Timeline is null) return;
        Timeline.SetProject(model.Project, model.State.Selection.ClipID, Zoom.Value);
        Timeline.SetPosition(model.Position);
        UndoButton.IsEnabled = model.State.CanUndo && !model.Busy;
        RedoButton.IsEnabled = model.State.CanRedo && !model.Busy;
        TempoBox.Text = (model.Project?.Tempo ?? 120).ToString("0.###", CultureInfo.CurrentCulture);
        SelectionName.Text = model.SelectedClip?.Name ?? "None";
        MoveBox.Text = (model.SelectedClip?.Position ?? 0).ToString("0.######", CultureInfo.CurrentCulture);
        TrimBox.Text = ((model.SelectedClip?.Position ?? 0) + (model.SelectedClip?.Duration ?? 0)).ToString("0.######", CultureInfo.CurrentCulture);
        ProjectInfo.Text = model.Project is null ? "No project loaded" : $"{model.Project.Tracks.Length} tracks · {model.Project.SampleRate:0} Hz · {model.Project.Duration:0.##} seconds";
        var unresolved = model.Project?.Tracks.Sum(t => t.UnresolvedAudioEvents.Length) ?? 0;
        if (unresolved > 0) ProjectInfo.Text += $" · {unresolved} unresolved events: native playback unavailable";
        Mixer.Children.Clear();
        foreach (var track in model.Project?.Tracks ?? []) AddChannel(track);
    }
    private void AddChannel(TrackView track)
    {
        var panel = new StackPanel { Margin = new Thickness(8), Width = 230 };
        var select = new Button { Content = track.Name, FontWeight = FontWeights.SemiBold, HorizontalContentAlignment = HorizontalAlignment.Left };
        select.Click += async (_, _) => await model.Command("selectTrack", trackID: track.Id);
        panel.Children.Add(select);
        var gainRow = new StackPanel { Orientation = Orientation.Horizontal };
        gainRow.Children.Add(new Label { Content = "Gain dB", Width = 65 });
        var gain = new TextBox { Text = track.GainDB.ToString("0.###", CultureInfo.CurrentCulture), Width = 70 };
        AutomationProperties.SetName(gain, track.Name + " gain decibels"); gainRow.Children.Add(gain);
        var applyGain = new Button { Content = "Set", Padding = new Thickness(10, 3, 10, 3) };
        applyGain.Click += async (_, _) => await Guard(() => model.Command("setGain", trackID: track.Id, value: Number(gain)));
        gainRow.Children.Add(applyGain); panel.Children.Add(gainRow);
        var panRow = new StackPanel { Orientation = Orientation.Horizontal };
        panRow.Children.Add(new Label { Content = "Pan", Width = 65 });
        var pan = new TextBox { Text = track.Pan.ToString("0.###", CultureInfo.CurrentCulture), Width = 70, ToolTip = "−1 left · 0 centre · 1 right" };
        AutomationProperties.SetName(pan, track.Name + " pan"); panRow.Children.Add(pan);
        var applyPan = new Button { Content = "Set", Padding = new Thickness(10, 3, 10, 3) };
        applyPan.Click += async (_, _) => await Guard(() => model.Command("setPan", trackID: track.Id, value: Number(pan)));
        panRow.Children.Add(applyPan); panel.Children.Add(panRow);
        var flags = new StackPanel { Orientation = Orientation.Horizontal };
        var mute = new CheckBox { Content = "Mute", IsChecked = track.IsMuted };
        var solo = new CheckBox { Content = "Solo", IsChecked = track.IsSolo };
        mute.Click += async (_, _) => await model.Command("toggleMute", trackID: track.Id);
        solo.Click += async (_, _) => await model.Command("toggleSolo", trackID: track.Id);
        flags.Children.Add(mute); flags.Children.Add(solo); panel.Children.Add(flags);
        Mixer.Children.Add(new Border { Child = panel, Background = (Brush)FindResource("PanelBrush"), Margin = new Thickness(0, 0, 8, 0), BorderThickness = new Thickness(track.Id == model.State.Selection.TrackID ? 2 : 1), BorderBrush = track.Id == model.State.Selection.TrackID ? Brushes.LightSteelBlue : Brushes.Transparent });
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
    private async void Play(object sender, RoutedEventArgs e) => await model.Play();
    private async void Pause(object sender, RoutedEventArgs e) => await model.Pause();
    private async void Stop(object sender, RoutedEventArgs e) => await model.Stop();
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
