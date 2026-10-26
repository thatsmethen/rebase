using Microsoft.Win32;
using System.ComponentModel;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Markup;
using System.Windows.Media;

namespace Rebase.Windows;

public sealed class SourceAudioWindow : Window
{
    [DllImport("dwmapi.dll", ExactSpelling = true)]
    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    private static extern int DwmSetWindowAttribute(IntPtr window, uint attribute, ref int value, uint bytes);
    private readonly StudioViewModel model;
    private readonly string projectID, eventID;
    private readonly TaskCompletionSource completion = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly TextBlock heading = new() { FontSize = 18, TextTrimming = TextTrimming.CharacterEllipsis };
    private readonly TextBlock details = new() { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 12, 0, 12) };
    private readonly TextBlock description = new() { TextWrapping = TextWrapping.Wrap, Foreground = Brushes.LightGray };
    private readonly TextBlock provenance = new() { TextWrapping = TextWrapping.Wrap, FontSize = 10, Foreground = Brushes.LightGray };
    private readonly TextBlock message = new() { TextWrapping = TextWrapping.Wrap, Foreground = Brushes.Khaki };
    private SourceInspectionSnapshot? inspection;
    private bool working;
    internal Task Completion => completion.Task;
    internal bool Working => working;
    internal string Message => message.Text;
    internal string Details => details.Text;
    internal string SelectedMode => (Modes.SelectedItem as SourceAuditionMode)?.Id ?? SourceAuditionMode.Original;
    internal ListBox Modes { get; } = new() { DisplayMemberPath = nameof(SourceAuditionMode.Name), Background = new SolidColorBrush(Color.FromRgb(30, 33, 36)),
        Foreground = Brushes.Gainsboro, BorderBrush = new SolidColorBrush(Color.FromRgb(63, 69, 75)), BorderThickness = new Thickness(1) };
    internal Button RefreshButton { get; } = new() { Content = "Check again", MinWidth = 88 };
    internal Button ExportButton { get; } = new() { Content = "Export WAV…", MinWidth = 90 };
    internal Button PlayButton { get; } = new() { Content = "Play", MinWidth = 64 };
    internal Button PauseButton { get; } = new() { Content = "Pause", MinWidth = 64 };
    internal Button StopButton { get; } = new() { Content = "Stop", MinWidth = 64 };
    internal Button CloseButton { get; } = new() { Content = "Close", MinWidth = 70 };
    internal TextBox PositionInput { get; } = new() { Width = 105, MinHeight = 26, Text = "0", VerticalContentAlignment = VerticalAlignment.Center };
    internal Button SeekButton { get; } = new() { Content = "Seek", MinWidth = 60 };
    internal string? SmokeExportPath { get; set; }

    public SourceAudioWindow(StudioViewModel model)
    {
        this.model = model;
        projectID = model.Project?.Id ?? throw new InvalidOperationException("Open a project first.");
        eventID = model.SelectedSourceEvent?.Id ?? throw new InvalidOperationException("Select a retained source event first.");
        inspection = model.SourceInspection;
        Title = "Source Audio — Rebase"; Width = 800; Height = 600; MinWidth = 740; MinHeight = 540;
        WindowStartupLocation = WindowStartupLocation.CenterOwner; ShowInTaskbar = false;
        Background = new SolidColorBrush(Color.FromRgb(40, 42, 44)); Foreground = Brushes.Gainsboro; FontFamily = new("Segoe UI"); FontSize = 12;
        SourceInitialized += (_, _) => { int enabled = 1; _ = DwmSetWindowAttribute(new WindowInteropHelper(this).Handle, 20, ref enabled, sizeof(int)); };
        Resources.Add(typeof(ListBoxItem), (Style)XamlReader.Parse("""
            <Style xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" TargetType="ListBoxItem">
              <Setter Property="Padding" Value="9,10"/><Setter Property="HorizontalContentAlignment" Value="Stretch"/>
              <Setter Property="Template"><Setter.Value><ControlTemplate TargetType="ListBoxItem"><Border Name="Body" Background="Transparent" BorderBrush="Transparent" BorderThickness="1" Padding="{TemplateBinding Padding}"><ContentPresenter/></Border><ControlTemplate.Triggers>
                <Trigger Property="IsSelected" Value="True"><Setter TargetName="Body" Property="Background" Value="#31525D"/></Trigger>
                <Trigger Property="IsMouseOver" Value="True"><Setter TargetName="Body" Property="BorderBrush" Value="#657783"/></Trigger>
                <Trigger Property="IsKeyboardFocusWithin" Value="True"><Setter TargetName="Body" Property="BorderBrush" Value="#5BC8DB"/></Trigger>
              </ControlTemplate.Triggers></ControlTemplate></Setter.Value></Setter>
            </Style>
            """));
        var panel = new Grid();
        foreach (var height in new[] { GridLength.Auto, new GridLength(1, GridUnitType.Star), GridLength.Auto, GridLength.Auto }) panel.RowDefinitions.Add(new() { Height = height });
        var header = new StackPanel { Margin = new Thickness(0, 0, 0, 14) }; header.Children.Add(heading);
        header.Children.Add(new TextBlock { Text = "Saved source playback", Foreground = Brushes.LightGray, Margin = new Thickness(0, 4, 0, 0) }); panel.Children.Add(header);
        var body = new Grid(); body.ColumnDefinitions.Add(new() { Width = new GridLength(260) }); body.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        Modes.ItemsSource = SourceAuditionMode.All; Modes.Margin = new Thickness(0, 0, 16, 0); body.Children.Add(Modes);
        var info = new StackPanel(); info.Children.Add(description); info.Children.Add(details);
        var seekRow = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 0, 0, 12) };
        seekRow.Children.Add(new TextBlock { Text = "Position (s)", VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 8, 0) });
        seekRow.Children.Add(PositionInput); seekRow.Children.Add(SeekButton); info.Children.Add(seekRow);
        AutomationProperties.SetName(PositionInput, "Source playback seconds"); AutomationProperties.SetName(SeekButton, "Seek source playback");
        info.Children.Add(new TextBlock { Text = "Source modes bypass project mixer, effects, routing and automation. Complete project playback is still unavailable for retained CPR events.", TextWrapping = TextWrapping.Wrap, Foreground = Brushes.LightGray, Margin = new Thickness(0, 0, 0, 16) });
        info.Children.Add(provenance);
        var scroller = new ScrollViewer { Content = info, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled };
        Grid.SetColumn(scroller, 1); body.Children.Add(scroller); Grid.SetRow(body, 1); panel.Children.Add(body);
        var messages = new ScrollViewer { Content = message, MaxHeight = 70, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, Margin = new Thickness(0, 12, 0, 8) };
        Grid.SetRow(messages, 2); panel.Children.Add(messages);
        var actions = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
        foreach (var button in new[] { RefreshButton, ExportButton, PlayButton, PauseButton, StopButton, CloseButton })
        { actions.Children.Add(button); AutomationProperties.SetName(button, button.Content.ToString()); }
        Grid.SetRow(actions, 3); panel.Children.Add(actions);
        Content = new Border { Background = Background, Padding = new Thickness(18), Child = panel };
        AutomationProperties.SetName(Modes, "Source playback mode");
        Modes.SelectionChanged += (_, _) => { if (!working) Refresh(); };
        Modes.SelectedItem = SourceAuditionMode.All.First(m => m.Id == model.SourcePlaybackMode);
        RefreshButton.Click += async (_, _) => await Act(async () => { await model.InspectSource(); inspection = model.SourceInspection; });
        PlayButton.Click += async (_, _) => await Act(() => model.AuditionSource(SelectedMode));
        PauseButton.Click += async (_, _) => await Act(model.Pause);
        StopButton.Click += async (_, _) =>
        {
            if (model.SourceStreamPreparing) { await model.Stop(); message.Text = model.Status; }
            else await Act(model.Stop);
        };
        SeekButton.Click += async (_, _) => await Seek();
        PositionInput.PreviewKeyDown += async (_, e) =>
        {
            if (e.Key == Key.Enter) { e.Handled = true; await Seek(); }
            else if (e.Key == Key.Escape) { e.Handled = true; PositionInput.Text = model.Position.ToString("0.#########", CultureInfo.CurrentCulture); }
        };
        ExportButton.Click += async (_, _) =>
        {
            var path = SmokeExportPath;
            if (path is null)
            {
                var dialog = new SaveFileDialog { Title = "Export source audition", Filter = "WAV audio (*.wav)|*.wav", AddExtension = true, DefaultExt = ".wav" };
                if (dialog.ShowDialog(this) != true) return;
                path = dialog.FileName;
            }
            await Act(() => model.RenderSourceTo(path, SelectedMode));
        };
        CloseButton.Click += (_, _) => Close();
        PreviewKeyDown += (_, e) => { if (e.Key == Key.Escape && !working && !model.Busy) { e.Handled = true; Close(); } };
        Closing += (_, e) => { if (working || model.Busy) { e.Cancel = true; message.Text = "Use Stop to cancel source preparation before closing."; } };
        Closed += (_, _) => { model.StateChanged -= SessionChanged; model.PropertyChanged -= ModelChanged; completion.TrySetResult(); };
        model.StateChanged += SessionChanged; model.PropertyChanged += ModelChanged; Refresh();
    }
    private bool SameSelection => model.Project?.Id == projectID && model.SelectedSourceEvent?.Id == eventID;
    private async Task Act(Func<Task> action)
    {
        if (working || model.Busy || !SameSelection) return;
        working = true; SetAvailability();
        try { await action(); message.Text = model.Status; }
        catch (Exception error) { model.Report(error); message.Text = error.Message; }
        finally { working = false; Refresh(keepMessage: true); }
    }
    private void SessionChanged() { if (!working) Refresh(); }
    private void ModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(model.Position) && !PositionInput.IsKeyboardFocusWithin)
            PositionInput.Text = model.Position.ToString("0.#########", CultureInfo.CurrentCulture);
        if (e.PropertyName is nameof(model.Busy) or nameof(model.Status) or nameof(model.SourceStreamPreparing)) SetAvailability();
    }
    private async Task Seek()
    {
        if (!SeekButton.IsEnabled) return;
        if (!double.TryParse(PositionInput.Text, NumberStyles.Float, CultureInfo.CurrentCulture, out var seconds) || !double.IsFinite(seconds) || seconds < 0)
        { message.Text = "Enter a finite source position of zero seconds or later."; return; }
        await Act(() => model.Seek(seconds));
        PositionInput.Text = model.Position.ToString("0.#########", CultureInfo.CurrentCulture);
    }
    private SourceModeAvailability? Availability => inspection?.Modes.FirstOrDefault(m => m.Mode == SelectedMode);
    private void Refresh(bool keepMessage = false)
    {
        var mode = SourceAuditionMode.Find(SelectedMode);
        heading.Text = SameSelection ? model.SelectedSourceEvent!.Name : "Source selection changed";
        heading.ToolTip = heading.Text; description.Text = mode.Description;
        var item = Availability;
        details.Text = item?.Available == true ? string.Format(CultureInfo.CurrentCulture,
            "Source rate    {0:0} Hz\nPlayback rate    {1:0} Hz\nDuration    {2:0.000000} s\nFrames    {3:N0}",
            item.SourceSampleRate, item.SampleRate, item.Frames / item.SampleRate, item.Frames) : "Preparation unavailable for this mode.";
        if (item?.ContributorCount is { } count) details.Text += $"\nContributors    {count}\nAudible fragments    {item.FragmentCount}";
        provenance.Text = inspection is null ? "Check the source again to inspect its playback modes." :
            "Source SHA-256\n" + inspection.SourceSHA256 + "\n\nEvery playback, resume, seek and export checks the original source and required attached media again. Export also writes its complete provenance beside the WAV.";
        if (!keepMessage) message.Text = !SameSelection || inspection?.Revision != model.State.Revision
            ? "The project or selection changed. Close this window and inspect the source again."
            : item?.Reason ?? item?.SnapshotExportReason ?? "Live streaming and snapshot export are available. Device output is checked when playback starts.";
        SetAvailability();
    }
    private void SetAvailability()
    {
        var idle = !working && !model.Busy;
        var current = SameSelection && inspection?.Revision == model.State.Revision;
        Modes.IsEnabled = idle; RefreshButton.IsEnabled = idle && SameSelection;
        PlayButton.IsEnabled = idle && current && Availability?.LiveAvailable == true;
        ExportButton.IsEnabled = idle && current && Availability?.SnapshotExportAvailable == true;
        PauseButton.IsEnabled = idle && model.IsSourceContext && model.IsPlaying;
        StopButton.IsEnabled = (idle || model.SourceStreamPreparing) && model.IsSourceContext;
        SeekButton.IsEnabled = PositionInput.IsEnabled = idle && current && model.IsSourceContext && model.SourcePlaybackMode == SelectedMode;
        CloseButton.IsEnabled = idle;
    }
}
