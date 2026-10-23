using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;

namespace Rebase.Windows;

/// Shows one bounded page at a time. All import semantics remain in the session.
public sealed class CPRReviewWindow : Window
{
    [DllImport("dwmapi.dll", ExactSpelling = true)]
    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    private static extern int DwmSetWindowAttribute(IntPtr window, uint attribute, ref int value, uint bytes);
    private readonly StudioViewModel model;
    private readonly Func<CPRReviewSnapshot, Task<bool>> import;
    private readonly List<CPRReviewSnapshot> pages;
    private readonly StackPanel rows = new();
    private readonly ScrollViewer scroll;
    private readonly ScrollViewer errorScroll;
    private readonly TextBlock pageLabel = new(), message = new() { TextWrapping = TextWrapping.Wrap };
    private readonly TaskCompletionSource completion = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private int index;
    private bool busy, finished;
    internal Button ImportButton { get; } = new() { Content = "Import Supported Data", MinWidth = 170 };
    internal Button PreviousButton { get; } = new() { Content = "Previous", MinWidth = 78 };
    internal Button NextButton { get; } = new() { Content = "Next", MinWidth = 78 };
    internal Button CloseButton { get; } = new() { Content = "Cancel", MinWidth = 82 };
    internal CPRReviewSnapshot CurrentPage => pages[index];
    internal string ReviewMessage => message.Text;
    internal bool Working => busy;
    internal Task Completion => completion.Task;
    internal int PagesVisited => pages.Count;
    internal ScrollViewer ReviewScroll => scroll;
    internal ScrollViewer ErrorScroll => errorScroll;
    internal FrameworkElement LastReviewItem => rows.Children.OfType<FrameworkElement>().Last();
    internal int? DarkCaptionResult { get; private set; }
    public CPRReviewSnapshot Review { get; }

    public CPRReviewWindow(StudioViewModel model, CPRReviewSnapshot first, Func<CPRReviewSnapshot, Task<bool>> import)
    {
        first.Validate(expectedOffset: 0);
        this.model = model; this.import = import; Review = first; pages = [first];
        Title = first.Historical ? "CPR Import Report — Rebase" : "Review CPR Import — Rebase";
        Width = 830; Height = 650; MinWidth = 650; MinHeight = 480;
        WindowStartupLocation = WindowStartupLocation.CenterOwner; ShowInTaskbar = false;
        Background = new SolidColorBrush(Color.FromRgb(40, 42, 44)); Foreground = Brushes.Gainsboro;
        FontFamily = new FontFamily("Segoe UI"); FontSize = 12;
        SourceInitialized += (_, _) =>
        {
            int enabled = 1;
            DarkCaptionResult = DwmSetWindowAttribute(new WindowInteropHelper(this).Handle, 20, ref enabled, sizeof(int));
        };
        var panel = new Grid();
        foreach (var height in new[] { GridLength.Auto, GridLength.Auto, new GridLength(1, GridUnitType.Star), GridLength.Auto, GridLength.Auto }) panel.RowDefinitions.Add(new() { Height = height });
        var heading = new StackPanel();
        heading.Children.Add(new TextBlock { Text = first.Historical ? "Preserved import report" : "Review supported CPR data", FontSize = 20, Foreground = Foreground, Margin = new Thickness(0, 0, 0, 10) });
        heading.Children.Add(new TextBlock { Text = first.SourceName, FontSize = 14, FontWeight = FontWeights.SemiBold, Foreground = Foreground, TextWrapping = TextWrapping.Wrap });
        heading.Children.Add(new TextBox { Text = "SHA-256  " + first.SourceSHA256, IsReadOnly = true, BorderThickness = new Thickness(0), Background = Brushes.Transparent, FontFamily = new FontFamily("Consolas"), FontSize = 11, Margin = new Thickness(0, 4, 0, 0), Padding = new Thickness(0), TextWrapping = TextWrapping.Wrap });
        heading.Children.Add(new TextBlock { Text = $"{first.SourceByteCount:N0} bytes · {first.InterpretationProfile}", Foreground = Brushes.LightGray, Margin = new Thickness(0, 3, 0, 8) });
        panel.Children.Add(heading);
        var summary = new TextBlock { Text = $"{first.RecoveredTrackCount} tracks · {first.RecoveredClipCount} editable clips · {first.UnresolvedEventCount} retained source events\n" +
            (first.Historical ? "Historical baseline; later project edits are not part of this report." : "Partial import: only established data is restored. Unsupported content remains in the preserved original."),
            TextWrapping = TextWrapping.Wrap, Foreground = Foreground, Margin = new Thickness(0, 0, 0, 12) };
        Grid.SetRow(summary, 1); panel.Children.Add(summary);
        scroll = new ScrollViewer { Content = rows, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, Background = new SolidColorBrush(Color.FromRgb(31, 34, 36)), Padding = new Thickness(12) };
        Grid.SetRow(scroll, 2); panel.Children.Add(scroll);
        var navigation = new DockPanel { Margin = new Thickness(0, 10, 0, 7) };
        var paging = new StackPanel { Orientation = Orientation.Horizontal };
        paging.Children.Add(PreviousButton); paging.Children.Add(NextButton); DockPanel.SetDock(paging, Dock.Right); navigation.Children.Add(paging);
        pageLabel.VerticalAlignment = VerticalAlignment.Center; pageLabel.Foreground = Brushes.LightGray; navigation.Children.Add(pageLabel);
        Grid.SetRow(navigation, 3); panel.Children.Add(navigation);
        var footer = new Grid(); footer.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); footer.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        message.Foreground = new SolidColorBrush(Color.FromRgb(218, 187, 124));
        errorScroll = new ScrollViewer { Content = message, MaxHeight = 80, Margin = new Thickness(0, 0, 12, 0),
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled };
        footer.Children.Add(errorScroll);
        var actions = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Bottom }; actions.Children.Add(CloseButton); actions.Children.Add(ImportButton); Grid.SetColumn(actions, 1); footer.Children.Add(actions); Grid.SetRow(footer, 4); panel.Children.Add(footer);
        // The content root owns the full opaque client surface. Padding belongs
        // inside this root so visual-tree captures include every footer control.
        Content = new Border { Background = Background, Padding = new Thickness(18), Child = panel };
        if (first.Historical) CloseButton.Content = "Close report";
        foreach (var button in new[] { PreviousButton, NextButton, CloseButton, ImportButton }) AutomationProperties.SetName(button, (string)button.Content);
        PreviousButton.Click += (_, _) => { if (!busy && index > 0) { index--; Display(); } };
        NextButton.Click += async (_, _) => await NextPage();
        ImportButton.Click += async (_, _) => await Import();
        CloseButton.Click += (_, _) => Close();
        PreviewKeyDown += (_, e) => { if (e.Key == Key.Escape) { e.Handled = true; Close(); } };
        Closing += OnClosing;
        Closed += (_, _) => completion.TrySetResult();
        Display();
    }
    private void Display()
    {
        var page = pages[index]; rows.Children.Clear();
        foreach (var item in page.Items)
        {
            var section = item.Section switch { "recovered" => "Recovered data", "tracks" => "Tracks", "unresolved" => "Unsupported / unresolved", "defaults" => "Application defaults", _ => "Metadata" };
            rows.Children.Add(new TextBlock { Text = section + " · " + item.Label, Foreground = Brushes.Gainsboro, FontWeight = FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 7, 0, 3) });
            rows.Children.Add(new TextBlock { Text = item.Detail, Foreground = Brushes.LightGray, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 9) });
        }
        if (page.Items.Length == 0) rows.Children.Add(new TextBlock { Text = "No review items.", Foreground = Foreground });
        pageLabel.Text = page.TotalItems == 0 ? "0 items" : $"Items {page.Offset + 1}–{page.Offset + page.Items.Length} of {page.TotalItems}";
        scroll.ScrollToTop(); SetBusy(busy);
    }
    private void SetBusy(bool value)
    {
        var active = model.CPRReview?.ReviewID == Review.ReviewID;
        busy = value; PreviousButton.IsEnabled = !value && index > 0;
        NextButton.IsEnabled = !value && (index + 1 < pages.Count || active && pages[index].NextOffset is not null);
        ImportButton.IsEnabled = !value && active && Review.CanImport && !Review.Historical;
        CloseButton.IsEnabled = !value;
    }
    private async Task NextPage()
    {
        if (busy) return;
        if (index + 1 < pages.Count) { index++; Display(); return; }
        if (pages[index].NextOffset is not { } next) return;
        SetBusy(true); message.Text = "Loading review page…";
        try
        {
            var page = await model.CPRReviewPage(Review, next);
            if (page is null) message.Text = model.Status;
            else { pages.Add(page); index++; message.Text = ""; Display(); }
        }
        finally { SetBusy(false); }
    }
    private async Task Import()
    {
        if (busy || model.CPRReview?.ReviewID != Review.ReviewID || !Review.CanImport || Review.Historical) return;
        SetBusy(true); message.Text = "";
        try
        {
            if (await import(Review)) { finished = true; Close(); }
            else message.Text = model.Status;
        }
        catch (Exception error) { model.Report(error); message.Text = error.Message; }
        finally { SetBusy(false); }
    }
    private async void OnClosing(object? sender, CancelEventArgs e)
    {
        if (finished) return;
        e.Cancel = true;
        if (busy) { message.Text = "Wait for the current operation to finish before closing."; return; }
        SetBusy(true);
        try { await model.CancelCPRReview(Review.ReviewID); }
        finally { finished = true; Close(); }
    }
}
