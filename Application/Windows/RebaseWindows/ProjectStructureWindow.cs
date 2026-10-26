using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Input;
using System.Windows.Media;

namespace Rebase.Windows;

public sealed class ProjectStructureWindow : Window
{
    internal TabControl Sections { get; } = new();
    internal Button CloseButton { get; } = new() { Content = "Close", MinWidth = 84 };
    internal TextBox CompleteJson { get; }
    internal Task Completion => completion.Task;
    private readonly TaskCompletionSource completion = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public ProjectStructureSnapshot Snapshot { get; }
    public ProjectStructureWindow(ProjectStructureSnapshot snapshot)
    {
        Snapshot = snapshot;
        Title = "Saved Project Structure — Rebase";
        Width = 930; Height = 690; MinWidth = 660; MinHeight = 480;
        WindowStartupLocation = WindowStartupLocation.CenterOwner; ShowInTaskbar = false;
        Background = new SolidColorBrush(Color.FromRgb(40, 42, 44)); Foreground = Brushes.Gainsboro;
        FontFamily = new FontFamily("Segoe UI"); FontSize = 12;
        Sections.Background = new SolidColorBrush(Color.FromRgb(31, 34, 36)); Sections.Foreground = Foreground;
        Sections.BorderBrush = new SolidColorBrush(Color.FromRgb(73, 80, 85));
        var tabStyle = new Style(typeof(TabItem));
        tabStyle.Setters.Add(new Setter(Control.ForegroundProperty, Foreground));
        tabStyle.Setters.Add(new Setter(Control.BackgroundProperty, new SolidColorBrush(Color.FromRgb(49, 54, 58))));
        var tabBorder = new FrameworkElementFactory(typeof(Border)); tabBorder.Name = "TabBorder";
        tabBorder.SetValue(Border.PaddingProperty, new Thickness(11, 7, 11, 7)); tabBorder.SetValue(Border.MarginProperty, new Thickness(0, 0, 2, 0));
        tabBorder.SetValue(Border.BorderThicknessProperty, new Thickness(1)); tabBorder.SetValue(Border.BorderBrushProperty, Brushes.Transparent);
        tabBorder.SetBinding(Border.BackgroundProperty, new Binding(nameof(Background)) { RelativeSource = RelativeSource.TemplatedParent });
        var header = new FrameworkElementFactory(typeof(ContentPresenter)); header.SetValue(ContentPresenter.ContentSourceProperty, "Header"); tabBorder.AppendChild(header);
        var tabTemplate = new ControlTemplate(typeof(TabItem)) { VisualTree = tabBorder };
        var selected = new Trigger { Property = TabItem.IsSelectedProperty, Value = true };
        selected.Setters.Add(new Setter(Border.BackgroundProperty, new SolidColorBrush(Color.FromRgb(47, 81, 91)), "TabBorder"));
        var focused = new Trigger { Property = IsKeyboardFocusWithinProperty, Value = true };
        focused.Setters.Add(new Setter(Border.BorderBrushProperty, new SolidColorBrush(Color.FromRgb(91, 200, 219)), "TabBorder"));
        tabTemplate.Triggers.Add(selected); tabTemplate.Triggers.Add(focused); tabStyle.Setters.Add(new Setter(Control.TemplateProperty, tabTemplate));
        Sections.ItemContainerStyle = tabStyle;
        var root = new Grid();
        root.RowDefinitions.Add(new() { Height = GridLength.Auto });
        root.RowDefinitions.Add(new() { Height = GridLength.Auto });
        root.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        root.RowDefinitions.Add(new() { Height = GridLength.Auto });
        root.Children.Add(new TextBlock { Text = "Saved project structure", FontSize = 21, Margin = new Thickness(0, 0, 0, 8) });
        var scope = new TextBlock { Text = ProjectStructureSnapshot.Scope, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 12) };
        Grid.SetRow(scope, 1); root.Children.Add(scope);
        var overview = ReadOnlyText($"Preserved source\n{snapshot.SourceByteCount:N0} bytes\nSHA-256 {snapshot.SourceSHA256}\n\n" +
            $"Complete report\n{snapshot.ReportByteCount:N0} bytes · schema 1\nSHA-256 {snapshot.ReportSHA256}\n\n" +
            $"{snapshot.Hierarchy.Count:N0} ordered hierarchy entries · {snapshot.ListCount:N0} lists\n{snapshot.Tracks.Count:N0} audio track bindings · {snapshot.ResourceAssociationCount:N0} resource associations\n{snapshot.ObjectCount:N0} native objects · {snapshot.Issues.Count:N0} issues\n\n" +
            $"Project {snapshot.ProjectID} · revision {snapshot.Revision}\nSaved manifest SHA-256 {snapshot.ProjectManifestSHA256}");
        Sections.Items.Add(new TabItem { Header = "Overview", Content = overview });
        Sections.Items.Add(new TabItem { Header = "Hierarchy", Content = Rows(snapshot.Hierarchy, "No counted hierarchy entries.") });
        Sections.Items.Add(new TabItem { Header = "Tracks", Content = Rows(snapshot.Tracks, "No audio track bindings were decoded. Other objects remain in the complete JSON.") });
        Sections.Items.Add(new TabItem { Header = "Issues", Content = Rows(snapshot.Issues, "No structural issues were reported. Runtime routing and processing are still unresolved.") });
        CompleteJson = ReadOnlyText(snapshot.Json); CompleteJson.FontFamily = new FontFamily("Consolas"); CompleteJson.FontSize = 11;
        CompleteJson.TextWrapping = TextWrapping.NoWrap;
        Sections.Items.Add(new TabItem { Header = "Complete JSON", Content = CompleteJson });
        Grid.SetRow(Sections, 2); root.Children.Add(Sections);
        var footer = new DockPanel { Margin = new Thickness(0, 12, 0, 0) };
        CloseButton.HorizontalAlignment = HorizontalAlignment.Right; DockPanel.SetDock(CloseButton, Dock.Right); footer.Children.Add(CloseButton);
        footer.Children.Add(new TextBlock { Text = "Read-only · complete report verified before display", VerticalAlignment = VerticalAlignment.Center, TextWrapping = TextWrapping.Wrap });
        Grid.SetRow(footer, 3); root.Children.Add(footer);
        Content = new Border { Background = Background, Padding = new Thickness(18), Child = root };
        AutomationProperties.SetName(Sections, "Saved project structure sections");
        AutomationProperties.SetName(CompleteJson, "Complete saved project structure JSON");
        AutomationProperties.SetName(CloseButton, "Close saved project structure");
        CloseButton.Click += (_, _) => Close();
        PreviewKeyDown += (_, e) => { if (e.Key == Key.Escape) { e.Handled = true; Close(); } };
        Closed += (_, _) => completion.TrySetResult();
    }
    private static TextBox ReadOnlyText(string text) => new() { Text = text, IsReadOnly = true, AcceptsReturn = true,
        VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Auto,
        TextWrapping = TextWrapping.Wrap, Padding = new Thickness(12), BorderThickness = new Thickness(0) };
    private static FrameworkElement Rows(IReadOnlyList<string> rows, string empty)
    {
        if (rows.Count == 0) return ReadOnlyText(empty);
        var list = new ListBox { ItemsSource = rows, Padding = new Thickness(4), BorderThickness = new Thickness(0),
            Background = new SolidColorBrush(Color.FromRgb(31, 34, 36)), Foreground = Brushes.Gainsboro };
        VirtualizingPanel.SetIsVirtualizing(list, true); VirtualizingPanel.SetVirtualizationMode(list, VirtualizationMode.Recycling);
        ScrollViewer.SetCanContentScroll(list, true); ScrollViewer.SetHorizontalScrollBarVisibility(list, ScrollBarVisibility.Disabled);
        var style = new Style(typeof(ListBoxItem)); style.Setters.Add(new Setter(Control.HorizontalContentAlignmentProperty, HorizontalAlignment.Stretch)); list.ItemContainerStyle = style;
        var factory = new FrameworkElementFactory(typeof(TextBlock)); factory.SetBinding(TextBlock.TextProperty, new Binding());
        factory.SetValue(TextBlock.TextWrappingProperty, TextWrapping.Wrap); factory.SetValue(FrameworkElement.MarginProperty, new Thickness(8));
        list.ItemTemplate = new DataTemplate { VisualTree = factory };
        return list;
    }
}
