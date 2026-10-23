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

/// Immediate shared edits; Close keeps successful edits in normal project history.
public sealed class AutomationEditorWindow : Window
{
    [DllImport("dwmapi.dll", ExactSpelling = true)]
    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    private static extern int DwmSetWindowAttribute(IntPtr window, uint attribute, ref int value, uint bytes);
    private readonly StudioViewModel model;
    private readonly string projectID;
    private readonly TaskCompletionSource completion = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly TextBlock heading = new() { FontSize = 18, TextTrimming = TextTrimming.CharacterEllipsis };
    private readonly TextBlock manualLabel = new(), valueLabel = new(), message = new() { TextWrapping = TextWrapping.Wrap, Foreground = Brushes.Khaki };
    private bool refreshing, working, available;
    private ulong draftRevision;
    private string? selectedID;
    internal string TrackID { get; }
    internal string Parameter => ParameterBox.SelectedIndex == 1 ? "pan" : "gainDB";
    internal Task Completion => completion.Task;
    internal bool Working => working;
    internal ulong DraftRevision => draftRevision;
    internal string Message => message.Text;
    internal string? SelectedPointID => selectedID;
    internal AutomationLaneView? Lane { get; private set; }
    internal AutomationCurve Curve { get; } = new();
    internal ListBox PointList { get; } = new() { Background = new SolidColorBrush(Color.FromRgb(30, 33, 36)), Foreground = Brushes.Gainsboro,
        BorderBrush = new SolidColorBrush(Color.FromRgb(63, 69, 75)), BorderThickness = new Thickness(1), DisplayMemberPath = nameof(AutomationPointView.Display) };
    internal ComboBox ParameterBox { get; } = new() { Width = 110, MinHeight = 30 };
    internal ComboBox InterpolationBox { get; } = new() { MinHeight = 30 };
    internal CheckBox ReadButton { get; } = new() { Content = "Read volume automation", VerticalAlignment = VerticalAlignment.Center };
    internal TextBox TimeBox { get; } = new();
    internal TextBox ValueBox { get; } = new();
    internal Button AddButton { get; } = new() { Content = "Add", MinWidth = 65 };
    internal Button UpdateButton { get; } = new() { Content = "Update", MinWidth = 65 };
    internal Button DeleteButton { get; } = new() { Content = "Delete", MinWidth = 65 };
    internal Button ResetButton { get; } = new() { Content = "New / reset fields" };
    internal Button UndoButton { get; } = new() { Content = "Undo", MinWidth = 60 };
    internal Button RedoButton { get; } = new() { Content = "Redo", MinWidth = 60 };
    internal Button CloseButton { get; } = new() { Content = "Close", MinWidth = 76 };

    public AutomationEditorWindow(StudioViewModel model, string trackID)
    {
        this.model = model; TrackID = trackID;
        projectID = model.Project?.Id ?? throw new InvalidOperationException("Open a project before editing automation.");
        Title = "Track Automation — Rebase"; Width = 840; Height = 680; MinWidth = 680; MinHeight = 560;
        WindowStartupLocation = WindowStartupLocation.CenterOwner; ShowInTaskbar = false;
        Background = new SolidColorBrush(Color.FromRgb(40, 42, 44)); Foreground = Brushes.Gainsboro; FontFamily = new("Segoe UI"); FontSize = 12;
        SourceInitialized += (_, _) => { int enabled = 1; _ = DwmSetWindowAttribute(new WindowInteropHelper(this).Handle, 20, ref enabled, sizeof(int)); };
        Resources.Add(typeof(ListBoxItem), (Style)XamlReader.Parse("""
            <Style xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" TargetType="ListBoxItem">
              <Setter Property="Padding" Value="7,5"/><Setter Property="HorizontalContentAlignment" Value="Stretch"/>
              <Setter Property="Template"><Setter.Value><ControlTemplate TargetType="ListBoxItem"><Border Name="Body" Background="Transparent" BorderBrush="Transparent" BorderThickness="1" Padding="{TemplateBinding Padding}"><ContentPresenter/></Border><ControlTemplate.Triggers>
                <Trigger Property="IsSelected" Value="True"><Setter TargetName="Body" Property="Background" Value="#31525D"/></Trigger>
                <Trigger Property="IsMouseOver" Value="True"><Setter TargetName="Body" Property="BorderBrush" Value="#657783"/></Trigger>
                <Trigger Property="IsKeyboardFocusWithin" Value="True"><Setter TargetName="Body" Property="BorderBrush" Value="#5BC8DB"/></Trigger>
              </ControlTemplate.Triggers></ControlTemplate></Setter.Value></Setter>
            </Style>
            """));
        ParameterBox.Items.Add(new ComboBoxItem { Content = "Volume" }); ParameterBox.Items.Add(new ComboBoxItem { Content = "Pan" }); ParameterBox.SelectedIndex = 0;
        InterpolationBox.Items.Add(new ComboBoxItem { Content = "Linear" }); InterpolationBox.Items.Add(new ComboBoxItem { Content = "Hold" }); InterpolationBox.SelectedIndex = 0;
        var panel = new Grid(); foreach (var height in new[] { GridLength.Auto, new GridLength(1, GridUnitType.Star), new GridLength(1, GridUnitType.Star), GridLength.Auto, GridLength.Auto }) panel.RowDefinitions.Add(new() { Height = height });
        var header = new StackPanel(); header.Children.Add(heading);
        var modes = new DockPanel { Margin = new Thickness(0, 6, 0, 6) };
        DockPanel.SetDock(ParameterBox, Dock.Left); modes.Children.Add(ParameterBox); modes.Children.Add(ReadButton); header.Children.Add(modes);
        panel.Children.Add(header);
        Curve.Margin = new Thickness(0, 0, 0, 8); Grid.SetRow(Curve, 1); panel.Children.Add(Curve);
        var body = new Grid { MinHeight = 160 }; body.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); body.ColumnDefinitions.Add(new() { Width = new GridLength(252) });
        PointList.Margin = new Thickness(0, 0, 10, 0); body.Children.Add(PointList);
        var fields = new StackPanel(); Grid.SetColumn(fields, 1); body.Children.Add(fields);
        var input = new Grid(); input.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); input.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        var timeColumn = new StackPanel(); timeColumn.Children.Add(new TextBlock { Text = "Time (seconds)", Margin = new Thickness(3, 0, 0, 2) }); timeColumn.Children.Add(TimeBox); input.Children.Add(timeColumn);
        var valueColumn = new StackPanel(); valueLabel.Margin = new Thickness(3, 0, 0, 2); valueColumn.Children.Add(valueLabel); valueColumn.Children.Add(ValueBox); Grid.SetColumn(valueColumn, 1); input.Children.Add(valueColumn); fields.Children.Add(input);
        fields.Children.Add(new TextBlock { Text = "Outgoing segment", Margin = new Thickness(3, 6, 0, 0) }); fields.Children.Add(InterpolationBox);
        var editButtons = new StackPanel { Orientation = Orientation.Horizontal }; editButtons.Children.Add(AddButton); editButtons.Children.Add(UpdateButton); editButtons.Children.Add(DeleteButton); fields.Children.Add(editButtons); fields.Children.Add(ResetButton);
        Grid.SetRow(body, 2); panel.Children.Add(body);
        var help = new StackPanel { Margin = new Thickness(0, 8, 0, 6) };
        manualLabel.TextWrapping = TextWrapping.Wrap; manualLabel.Foreground = Brushes.LightGray; help.Children.Add(manualLabel);
        help.Children.Add(new TextBlock { Text = "Click the curve to add a point, or enter exact values. Add replaces any point at the same time. Changes enter project undo history immediately.", FontSize = 11, TextWrapping = TextWrapping.Wrap, Foreground = Brushes.LightGray }); Grid.SetRow(help, 3); panel.Children.Add(help);
        var footer = new DockPanel(); var actions = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Bottom }; actions.Children.Add(UndoButton); actions.Children.Add(RedoButton); actions.Children.Add(CloseButton); DockPanel.SetDock(actions, Dock.Right); footer.Children.Add(actions);
        footer.Children.Add(new ScrollViewer { Content = message, MaxHeight = 54, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, Margin = new Thickness(0, 0, 8, 0) }); Grid.SetRow(footer, 4); panel.Children.Add(footer);
        Content = new Border { Background = Background, Padding = new Thickness(14), Child = panel };
        foreach (var (element, name) in new (DependencyObject, string)[] { (ParameterBox, "Automation parameter"), (PointList, "Automation points"), (TimeBox, "Automation time in seconds"), (ValueBox, "Automation value"), (InterpolationBox, "Outgoing interpolation"), (Curve, "Automation curve; click to add a point") }) AutomationProperties.SetName(element, name);
        foreach (var button in new[] { AddButton, UpdateButton, DeleteButton, ResetButton, UndoButton, RedoButton, CloseButton }) AutomationProperties.SetName(button, button.Content.ToString());
        ParameterBox.SelectionChanged += (_, _) => { if (!refreshing && !working) { selectedID = null; Refresh(true); message.Text = ""; } };
        PointList.SelectionChanged += (_, _) => { if (!refreshing && !working) { selectedID = (PointList.SelectedItem as AutomationPointView)?.Id; RefreshFields(); SetAvailability(); } };
        AddButton.Click += async (_, _) => await ApplyPoint(false);
        UpdateButton.Click += async (_, _) => await ApplyPoint(true);
        DeleteButton.Click += async (_, _) => { if (selectedID is { } id) await Act(() => model.RemoveAutomationPoint(TrackID, id, draftRevision, Parameter), null); };
        ResetButton.Click += (_, _) => { if (!working) { selectedID = null; Refresh(true); message.Text = ""; TimeBox.Focus(); } };
        UndoButton.Click += async (_, _) => await History("undo"); RedoButton.Click += async (_, _) => await History("redo");
        ReadButton.Checked += ReadChanged; ReadButton.Unchecked += ReadChanged;
        Curve.InsertRequested += async (time, value) => await Act(() => model.UpsertAutomationPoint(TrackID, null, time, value, "linear", model.State.Revision, Parameter), time);
        CloseButton.Click += (_, _) => Close();
        foreach (var field in new[] { TimeBox, ValueBox }) field.PreviewKeyDown += async (_, e) =>
        {
            if (e.Key == Key.Enter) { e.Handled = true; await ApplyPoint(selectedID is not null); }
            else if (e.Key == Key.Escape) { e.Handled = true; Refresh(true); message.Text = ""; }
        };
        PreviewKeyDown += async (_, e) =>
        {
            if (e.Handled || working) return;
            if (e.Key == Key.Escape && e.OriginalSource is not TextBox) { e.Handled = true; Close(); }
            if (Keyboard.Modifiers == ModifierKeys.Control && e.OriginalSource is not TextBox && e.Key is Key.Z or Key.Y)
            { e.Handled = true; await History(e.Key == Key.Z ? "undo" : "redo"); }
        };
        Closing += (_, e) => { if (working || model.Busy) { e.Cancel = true; message.Text = "Wait for the current edit to finish before closing."; } };
        Closed += (_, _) => { model.StateChanged -= SessionChanged; model.PropertyChanged -= ModelChanged; completion.TrySetResult(); };
        model.StateChanged += SessionChanged; model.PropertyChanged += ModelChanged;
        Refresh(true);
    }
    private TrackView? Track => model.Project?.Id == projectID ? model.Project.Tracks.FirstOrDefault(track => track.Id == TrackID) : null;
    private void SessionChanged() { if (!working) { Refresh(false); if (model.State.Revision != draftRevision) message.Text = "Project state changed. Reset fields before applying an existing draft."; } }
    private void ModelChanged(object? sender, PropertyChangedEventArgs e) { if (e.PropertyName == nameof(model.Busy)) SetAvailability(); }
    private void Refresh(bool resetFields)
    {
        refreshing = true;
        try
        {
            var track = Track; available = track is not null;
            heading.Text = track?.Name ?? "Track unavailable"; heading.ToolTip = heading.Text;
            Lane = track is null ? null : AutomationLaneView.Read(track, Parameter);
            PointList.ItemsSource = Lane?.Points ?? [];
            PointList.SelectedItem = Lane?.Points.FirstOrDefault(point => point.Id == selectedID);
            ReadButton.Content = Parameter == "gainDB" ? "Read volume automation" : "Read pan automation";
            AutomationProperties.SetName(ReadButton, (string)ReadButton.Content);
            ReadButton.IsChecked = Lane?.IsReadEnabled ?? true;
            valueLabel.Text = Parameter == "gainDB" ? "Level (dB)" : "Pan (−1 L to +1 R)";
            AutomationProperties.SetName(ValueBox, valueLabel.Text);
            var manual = Parameter == "gainDB" ? track?.GainDB ?? 0 : track?.Pan ?? 0;
            manualLabel.Text = $"Manual {(Parameter == "gainDB" ? "volume" : "pan")}: {manual:0.###}{(Parameter == "gainDB" ? " dB" : "")} · " +
                (Lane?.IsReadEnabled == false ? "Read is off; playback uses the manual value." : Lane?.Points.Count > 0 ? "Read is on; playback follows this curve." : "No points; playback uses the manual value.");
            Curve.Set(Lane, Parameter, manual, model.Project?.Duration ?? 1, selectedID);
            if (resetFields) RefreshFields();
        }
        catch (Exception error) { available = false; Lane = null; model.Report(error); message.Text = error.Message; }
        finally { refreshing = false; SetAvailability(); }
    }
    private void RefreshFields()
    {
        var point = Lane?.Points.FirstOrDefault(item => item.Id == selectedID); selectedID = point?.Id;
        TimeBox.Text = (point?.Time ?? Math.Clamp(model.Position, 0, 86400)).ToString("R", CultureInfo.CurrentCulture);
        ValueBox.Text = (point?.Value ?? (Parameter == "gainDB" ? Track?.GainDB ?? 0 : Track?.Pan ?? 0)).ToString("R", CultureInfo.CurrentCulture);
        InterpolationBox.SelectedIndex = point?.Interpolation == "step" ? 1 : 0;
        draftRevision = model.State.Revision;
        Curve.Set(Lane, Parameter, Parameter == "gainDB" ? Track?.GainDB ?? 0 : Track?.Pan ?? 0, model.Project?.Duration ?? 1, selectedID);
    }
    private void SetAvailability()
    {
        var enabled = available && !working && !model.Busy;
        ParameterBox.IsEnabled = !working && !model.Busy; PointList.IsEnabled = enabled; Curve.IsEnabled = enabled;
        TimeBox.IsEnabled = ValueBox.IsEnabled = InterpolationBox.IsEnabled = AddButton.IsEnabled = ReadButton.IsEnabled = ResetButton.IsEnabled = enabled;
        UpdateButton.IsEnabled = DeleteButton.IsEnabled = enabled && Lane?.Points.Any(point => point.Id == selectedID) == true;
        UndoButton.IsEnabled = enabled && model.State.CanUndo; RedoButton.IsEnabled = enabled && model.State.CanRedo;
        CloseButton.IsEnabled = !working && !model.Busy;
    }
    private async Task ApplyPoint(bool update)
    {
        if (working || !available || model.Busy || update && selectedID is null) return;
        if (!double.TryParse(TimeBox.Text, NumberStyles.Float, CultureInfo.CurrentCulture, out var time) || !double.IsFinite(time) || time < 0 || time > 86400 ||
            !double.TryParse(ValueBox.Text, NumberStyles.Float, CultureInfo.CurrentCulture, out var value) || !double.IsFinite(value) || value < Curve.Minimum || value > Curve.Maximum)
        { message.Text = $"Enter a finite time from 0 to 86400 seconds and a value from {Curve.Minimum} to {Curve.Maximum}."; return; }
        var id = update ? selectedID : null; var interpolation = InterpolationBox.SelectedIndex == 1 ? "step" : "linear";
        await Act(() => model.UpsertAutomationPoint(TrackID, id, time, value, interpolation, draftRevision, Parameter), time);
    }
    private async Task History(string command) => await Act(() => model.AutomationHistory(command, TrackID, model.State.Revision), null);
    private async void ReadChanged(object sender, RoutedEventArgs e)
    {
        if (refreshing || working || model.Busy || !available) return;
        var enabled = ReadButton.IsChecked == true;
        await Act(() => model.SetAutomationRead(TrackID, enabled, model.State.Revision, Parameter), null);
    }
    private async Task Act(Func<Task<bool>> action, double? selectTime)
    {
        if (working || model.Busy || !available) return;
        var focus = Keyboard.FocusedElement as FrameworkElement;
        working = true; message.Text = ""; SetAvailability();
        try
        {
            if (await action())
            {
                Lane = Track is { } track ? AutomationLaneView.Read(track, Parameter) : null;
                if (selectTime is { } time) selectedID = Lane?.Points.FirstOrDefault(point => point.Time == time)?.Id;
                Refresh(true);
            }
            else { Refresh(false); message.Text = model.Status; }
        }
        catch (Exception error) { model.Report(error); Refresh(false); message.Text = error.Message; }
        finally { working = false; SetAvailability(); if (focus is { IsVisible: true, IsEnabled: true }) focus.Focus(); }
    }
}
