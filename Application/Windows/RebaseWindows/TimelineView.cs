using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Shapes;

namespace Rebase.Windows;

public sealed class TimelineView : Canvas
{
    private const double Header = 198, Ruler = 26;
    private double rowHeight = 44;
    internal double RowHeight => rowHeight;
    internal const double TrimHitWidth = 10;
    public static readonly Color[] TrackColors = [Color.FromRgb(177, 201, 102), Color.FromRgb(141, 175, 210), Color.FromRgb(209, 175, 101), Color.FromRgb(166, 151, 207)];
    private readonly Dictionary<string, WaveformVisual> waveformViews = [];
    private readonly List<FrameworkElement> headers = [];
    private readonly List<UIElement> rulerViews = [];
    private RulerSnapshot? musicalRuler;
    private bool musical = true;
    private readonly TextBlock rulerMode = new() { FontSize = 10, Margin = new Thickness(20, 5, 0, 0), Foreground = Brushes.Silver, IsHitTestVisible = false };
    private readonly Border headerCorner = new() { Width = Header, Height = Ruler, Background = new SolidColorBrush(Color.FromRgb(46, 49, 52)), BorderBrush = new SolidColorBrush(Color.FromRgb(29, 31, 33)), BorderThickness = new Thickness(0, 0, 1, 1) };
    private IReadOnlyDictionary<string, float[]> peaks = new Dictionary<string, float[]>();
    private double viewport, viewportHeight, currentPosition, horizontalOffset;
    private readonly Line playhead = new() { Stroke = Brushes.White, StrokeThickness = 1.5, IsHitTestVisible = false };
    private ProjectView? project;
    private string? selected, selectedTrack;
    private double pixels = 40;
    public event Action<string>? ClipSelected;
    public event Action<string, double, bool>? ClipDragged;
    public event Action<double>? SeekRequested;
    public event Action<string>? TrackSelected;
    public event Action<string, bool>? TrackFlagChanged;
    public TimelineView() { Background = new SolidColorBrush(Color.FromRgb(75, 77, 80)); ClipToBounds = true; MouseLeftButtonDown += EmptyClick; headerCorner.Child = rulerMode; }
    public void SetProject(ProjectView? value, string? selectedID, string? selectedTrackID, double pixelsPerSecond)
    {
        project = value; selected = selectedID; selectedTrack = selectedTrackID; pixels = pixelsPerSecond; Rebuild();
    }
    public void SetRowHeight(double value)
    {
        if (value is not (44 or 68)) throw new ArgumentOutOfRangeException(nameof(value));
        if (value == rowHeight) return;
        if (IsMouseCaptureWithin) throw new InvalidOperationException("Finish the event drag before changing row density.");
        rowHeight = value; Rebuild();
    }
    public void SetViewport(double width, double height)
    {
        if (!double.IsFinite(width) || !double.IsFinite(height) || width <= 0 || height <= 0) throw new ArgumentOutOfRangeException(nameof(width));
        if (viewport == width && viewportHeight == height) return;
        viewport = width; viewportHeight = height;
        Width = Math.Max(viewport, Header + Math.Max(24, project?.Duration ?? 24) * pixels + 40);
        Height = Math.Max(viewportHeight, Ruler + (project?.Tracks.Length ?? 0) * rowHeight);
        RebuildRuler(); SetPosition(currentPosition);
    }
    // Keep one vertical coordinate system for headers and events. Opaque header
    // panels counter the horizontal scroll; their controls stay hit-testable and
    // the event canvas/ruler scroll underneath without a second vertical viewer.
    public void SetHorizontalOffset(double value)
    {
        horizontalOffset = Math.Max(0, value);
        foreach (var header in headers) SetLeft(header, horizontalOffset);
        SetLeft(headerCorner, horizontalOffset);
    }
    internal IReadOnlyList<FrameworkElement> TrackHeaders => headers;
    public void SetRuler(RulerSnapshot? value, bool useMusical, string? error)
    {
        musicalRuler = value; musical = useMusical;
        rulerMode.Text = musical ? (value is null ? "Bars + Beats …" : "Bars + Beats") : "Seconds";
        if (musical && error is not null) rulerMode.Text = "Ruler unavailable";
        headerCorner.ToolTip = musical ? error : null;
        RebuildRuler();
    }
    internal bool MusicalRulerVisible => musical && musicalRuler is not null && musicalRuler.PixelsPerSecond == pixels && rulerViews.Count > 0;
    public void SetWaveforms(IReadOnlyDictionary<string, float[]> value)
    {
        peaks = value;
        foreach (var (id, visual) in waveformViews) visual.SetPeaks(peaks.TryGetValue(id, out var data) ? data : []);
    }
    public int PopulatedWaveformCount => waveformViews.Values.Count(view => view.HasPeaks && view.ActualWidth > 0 && view.ActualHeight > 0);
    public double TracksBottom => Ruler + (project?.Tracks.Length ?? 0) * rowHeight;
    public void SetPosition(double seconds)
    {
        currentPosition = seconds;
        playhead.X1 = playhead.X2 = Header + seconds * pixels;
        playhead.Y1 = Ruler; playhead.Y2 = Height;
    }
    private void EmptyClick(object sender, MouseButtonEventArgs e)
    {
        if (e.Handled || project is null) return;
        var x = e.GetPosition(this).X;
        if (x >= Header + horizontalOffset) { SeekRequested?.Invoke(Math.Max(0, (x - Header) / pixels)); e.Handled = true; }
    }
    private void Rebuild()
    {
        Children.Clear();
        headers.Clear();
        rulerViews.Clear();
        waveformViews.Clear();
        var duration = Math.Max(24, project?.Duration ?? 24);
        Width = Math.Max(viewport, Header + duration * pixels + 40);
        Height = Math.Max(viewportHeight, Ruler + (project?.Tracks.Length ?? 0) * rowHeight);
        RebuildRuler();
        if (project is not null)
        {
            for (var index = 0; index < project.Tracks.Length; ++index)
            {
                var compact = rowHeight == 44;
                var track = project.Tracks[index]; var top = Ruler + index * rowHeight;
                var divider = new Line { X1 = 0, X2 = Width, Y1 = top + rowHeight, Y2 = top + rowHeight, Stroke = new SolidColorBrush(Color.FromRgb(41, 43, 45)), IsHitTestVisible = false };
                Children.Add(divider);
                var header = new Grid { Width = Header, Height = rowHeight, Background = new SolidColorBrush(track.Id == selectedTrack ? Color.FromRgb(87, 92, 95) : Color.FromRgb(52, 55, 58)), Tag = track.Id };
                header.Children.Add(new Border { Background = new SolidColorBrush(TrackColors[index % TrackColors.Length]), Width = 13, HorizontalAlignment = HorizontalAlignment.Left });
                header.Children.Add(new Border { BorderBrush = new SolidColorBrush(Color.FromRgb(29, 31, 33)), BorderThickness = new Thickness(0, 0, 1, 1), IsHitTestVisible = false });
                var name = new Button { Content = track.Name, HorizontalContentAlignment = HorizontalAlignment.Left, FontSize = compact ? 10 : 11, Width = Header - 33, Height = compact ? 20 : 25, MinHeight = compact ? 20 : 25, Padding = new Thickness(3, 1, 3, 1),
                    Margin = new Thickness(21, compact ? 0 : 2, 3, 0), HorizontalAlignment = HorizontalAlignment.Left, VerticalAlignment = VerticalAlignment.Top, Background = Brushes.Transparent, BorderBrush = Brushes.Transparent };
                name.Click += (_, _) => TrackSelected?.Invoke(track.Id); header.Children.Add(name);
                var flags = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(23, compact ? 21 : 32, 0, 0), VerticalAlignment = VerticalAlignment.Top };
                var mute = new CheckBox { Content = "M", IsChecked = track.IsMuted, Padding = new Thickness(4, 1, 4, 1), MinWidth = 25, Height = compact ? 18 : 22, FontSize = compact ? 10 : 11, Margin = new Thickness(1), ToolTip = "Mute " + track.Name };
                var solo = new CheckBox { Content = "S", IsChecked = track.IsSolo, Padding = new Thickness(4, 1, 4, 1), MinWidth = 25, Height = compact ? 18 : 22, FontSize = compact ? 10 : 11, Margin = new Thickness(1), ToolTip = "Solo " + track.Name };
                AutomationProperties.SetName(mute, "Mute " + track.Name); AutomationProperties.SetName(solo, "Solo " + track.Name);
                RoutedEventHandler muteChanged = (_, _) => TrackFlagChanged?.Invoke(track.Id, false);
                RoutedEventHandler soloChanged = (_, _) => TrackFlagChanged?.Invoke(track.Id, true);
                mute.Checked += muteChanged; mute.Unchecked += muteChanged;
                solo.Checked += soloChanged; solo.Unchecked += soloChanged;
                flags.Children.Add(mute); flags.Children.Add(solo); flags.Children.Add(new TextBlock { Text = $" {track.Clips.Length} clips", Foreground = Brushes.Silver, VerticalAlignment = VerticalAlignment.Center, FontSize = 9 });
                header.Children.Add(flags); SetLeft(header, horizontalOffset); SetTop(header, top); SetZIndex(header, 2); Children.Add(header); headers.Add(header);
                foreach (var clip in track.Clips)
                {
                    var color = TrackColors[index % TrackColors.Length];
                    var content = new Grid { IsHitTestVisible = false };
                    content.RowDefinitions.Add(new RowDefinition { Height = new GridLength(compact ? 16 : 20) });
                    content.RowDefinitions.Add(new RowDefinition());
                    content.Children.Add(new TextBlock { Text = clip.Name, Foreground = Brushes.Black, TextTrimming = TextTrimming.CharacterEllipsis, Margin = new Thickness(6, compact ? 0 : 2, 4, 0), FontSize = compact ? 10 : 11 });
                    var waveform = new WaveformVisual();
                    waveform.SetPeaks(peaks.TryGetValue(clip.Id, out var data) ? data : []);
                    Grid.SetRow(waveform, 1); content.Children.Add(waveform); waveformViews[clip.Id] = waveform;
                    var button = new Button
                    {
                        Content = content,
                        Style = (Style)FindResource("AccentSurfaceButton"),
                        Width = Math.Max(16, clip.Duration * pixels), Height = rowHeight - (compact ? 6 : 10), Padding = new Thickness(0),
                        Margin = new Thickness(0), HorizontalContentAlignment = HorizontalAlignment.Stretch, VerticalContentAlignment = VerticalAlignment.Stretch,
                        Background = new SolidColorBrush(color), Foreground = Brushes.Black,
                        BorderThickness = new Thickness(1),
                        BorderBrush = clip.Id == selected ? Brushes.White : new SolidColorBrush(Color.FromRgb(51, 59, 37)),
                        Opacity = track.IsMuted ? 0.45 : 1,
                        ToolTip = $"{clip.Name} · {clip.Position:0.###}s · {clip.Duration:0.###}s. Drag to move; drag the right edge to trim."
                    };
                    AutomationProperties.SetName(button, $"{track.Name}, {clip.Name}, starts {clip.Position:0.###} seconds, duration {clip.Duration:0.###} seconds");
                    SetLeft(button, Header + clip.Position * pixels); SetTop(button, top + (compact ? 3 : 5)); Children.Add(button);
                    Point start = default; bool dragging = false, trim = false;
                    button.PreviewMouseLeftButtonDown += (_, e) =>
                    {
                        start = e.GetPosition(this); trim = e.GetPosition(button).X > button.ActualWidth - TrimHitWidth;
                        dragging = true; button.CaptureMouse(); e.Handled = true;
                    };
                    button.PreviewMouseMove += (_, e) =>
                    {
                        if (!dragging || e.LeftButton != MouseButtonState.Pressed) return;
                        var delta = e.GetPosition(this).X - start.X;
                        if (trim) button.Width = Math.Max(16, clip.Duration * pixels + delta);
                        else SetLeft(button, Math.Max(Header, Header + clip.Position * pixels + delta));
                    };
                    button.PreviewMouseLeftButtonUp += (_, e) =>
                    {
                        if (!dragging) return;
                        dragging = false; button.ReleaseMouseCapture(); e.Handled = true;
                        var delta = e.GetPosition(this).X - start.X;
                        if (Math.Abs(delta) < 3) ClipSelected?.Invoke(clip.Id);
                        else ClipDragged?.Invoke(clip.Id, (trim ? clip.Position + clip.Duration : clip.Position) + delta / pixels, trim);
                        // Display a preview only. The authoritative reply rebuilds
                        // geometry; grid snapping and media limits live in Swift.
                        button.Width = Math.Max(16, clip.Duration * pixels);
                        SetLeft(button, Header + clip.Position * pixels);
                    };
                    button.Click += (_, _) => ClipSelected?.Invoke(clip.Id); // Keyboard activation.
                }
            }
        }
        SetLeft(headerCorner, horizontalOffset); SetTop(headerCorner, 0); SetZIndex(headerCorner, 3); Children.Add(headerCorner);
        Children.Add(playhead); SetPosition(currentPosition);
    }
    private void RebuildRuler()
    {
        foreach (var view in rulerViews) Children.Remove(view);
        rulerViews.Clear();
        var duration = Math.Max(24, project?.Duration ?? 24);
        if (musical)
        {
            if (musicalRuler is null || musicalRuler.PixelsPerSecond != pixels || musicalRuler.Duration != duration) return;
            double lastLabel = double.NegativeInfinity;
            foreach (var tick in musicalRuler.Ticks)
            {
                bool label = tick.Bar && tick.Seconds * pixels - lastLabel >= 55;
                AddTick(tick.Seconds, tick.Bar, label ? tick.Label : null, tick);
                if (label) lastLabel = tick.Seconds * pixels;
            }
        }
        else
        {
            var step = Math.Max(1, Math.Ceiling(duration / 150));
            for (double seconds = 0; seconds <= duration; seconds += step)
                AddTick(seconds, true, seconds.ToString("0.##", System.Globalization.CultureInfo.InvariantCulture), null);
        }
    }
    private void AddTick(double seconds, bool major, string? text, RulerTick? tick)
    {
        var x = Header + seconds * pixels;
        var line = new Line { X1 = x, X2 = x, Y1 = 0, Y2 = Height, Stroke = new SolidColorBrush(major ? Color.FromRgb(103, 105, 108) : Color.FromRgb(88, 90, 93)), StrokeThickness = major ? 0.8 : 0.5, IsHitTestVisible = false };
        SetZIndex(line, -1); Children.Add(line); rulerViews.Add(line);
        if (text is null) return;
        var label = new TextBlock { Text = text, Foreground = Brushes.LightGray, FontSize = 10, IsHitTestVisible = false, Tag = tick };
        SetLeft(label, x + 4); SetTop(label, 5); Children.Add(label); rulerViews.Add(label);
    }
}

// Geometry comes only from checked shared source envelopes. No decorative or
// synthesized signal is drawn when media is unavailable.
public sealed class WaveformVisual : FrameworkElement
{
    private float[] peaks = [];
    public bool HasPeaks => peaks.Length > 0;
    public WaveformVisual() { IsHitTestVisible = false; ClipToBounds = true; }
    public void SetPeaks(float[] value) { peaks = value; InvalidateVisual(); }
    protected override void OnRender(DrawingContext context)
    {
        base.OnRender(context);
        if (peaks.Length == 0 || ActualWidth <= 0 || ActualHeight <= 0) return;
        int columns = Math.Max(1, Math.Min(peaks.Length, (int)(ActualWidth / 2)));
        var geometry = new StreamGeometry();
        var middle = ActualHeight / 2;
        using (var drawing = geometry.Open())
        {
            for (int column = 0; column < columns; column++)
            {
                int first = column * peaks.Length / columns, end = Math.Max(first + 1, (column + 1) * peaks.Length / columns);
                float peak = 0;
                for (int sample = first; sample < Math.Min(end, peaks.Length); sample++) peak = Math.Max(peak, Math.Min(1, peaks[sample]));
                var amplitude = Math.Max(0.5, peak * Math.Max(0, middle - 2));
                var x = (column + 0.5) * ActualWidth / columns;
                drawing.BeginFigure(new Point(x, middle - amplitude), false, false);
                drawing.LineTo(new Point(x, middle + amplitude), true, false);
            }
        }
        geometry.Freeze();
        context.DrawGeometry(null, new Pen(new SolidColorBrush(Color.FromArgb(205, 22, 35, 42)), 1), geometry);
    }
}
