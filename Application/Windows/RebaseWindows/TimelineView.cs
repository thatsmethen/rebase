using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Shapes;

namespace Rebase.Windows;

public sealed class TimelineView : Canvas
{
    private const double Header = 228, Row = 68, Ruler = 26;
    public static readonly Color[] TrackColors = [Color.FromRgb(177, 201, 102), Color.FromRgb(141, 175, 210), Color.FromRgb(209, 175, 101), Color.FromRgb(166, 151, 207)];
    private readonly Dictionary<string, WaveformVisual> waveformViews = [];
    private IReadOnlyDictionary<string, float[]> peaks = new Dictionary<string, float[]>();
    private double viewport, currentPosition;
    private readonly Line playhead = new() { Stroke = Brushes.White, StrokeThickness = 1.5, IsHitTestVisible = false };
    private ProjectView? project;
    private string? selected;
    private double pixels = 40;
    public event Action<string>? ClipSelected;
    public event Action<string, double, bool>? ClipDragged;
    public event Action<double>? SeekRequested;
    public event Action<string>? TrackSelected;
    public event Action<string, bool>? TrackFlagChanged;
    public TimelineView() { Background = new SolidColorBrush(Color.FromRgb(75, 77, 80)); ClipToBounds = true; MouseLeftButtonDown += EmptyClick; }
    public void SetProject(ProjectView? value, string? selectedID, double pixelsPerSecond)
    {
        project = value; selected = selectedID; pixels = pixelsPerSecond; Rebuild();
    }
    public void SetViewport(double width) { viewport = width; Width = Math.Max(viewport, Header + Math.Max(24, project?.Duration ?? 24) * pixels + 40); }
    public void SetWaveforms(IReadOnlyDictionary<string, float[]> value)
    {
        peaks = value;
        foreach (var (id, visual) in waveformViews) visual.SetPeaks(peaks.TryGetValue(id, out var data) ? data : []);
    }
    public int PopulatedWaveformCount => waveformViews.Values.Count(view => view.HasPeaks && view.ActualWidth > 0 && view.ActualHeight > 0);
    public double TracksBottom => Ruler + (project?.Tracks.Length ?? 0) * Row;
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
        if (x >= Header) { SeekRequested?.Invoke(Math.Max(0, (x - Header) / pixels)); e.Handled = true; }
    }
    private void Rebuild()
    {
        Children.Clear();
        waveformViews.Clear();
        var duration = Math.Max(24, project?.Duration ?? 24);
        Width = Math.Max(viewport, Header + duration * pixels + 40);
        Height = Ruler + Math.Max(4, project?.Tracks.Length ?? 0) * Row;
        var tickStep = Math.Max(1, Math.Ceiling(duration / 150));
        for (double t = 0; t <= duration; t += tickStep)
        {
            var x = Header + t * pixels;
            var line = new Line { X1 = x, X2 = x, Y1 = 0, Y2 = Height, Stroke = new SolidColorBrush(Color.FromRgb(103, 105, 108)), StrokeThickness = 0.5, IsHitTestVisible = false };
            Children.Add(line);
            var label = new TextBlock { Text = t.ToString("0.##", System.Globalization.CultureInfo.InvariantCulture), Foreground = Brushes.LightGray, FontSize = 10, IsHitTestVisible = false };
            SetLeft(label, x + 4); SetTop(label, 5); Children.Add(label);
        }
        if (project is not null)
        {
            for (var index = 0; index < project.Tracks.Length; ++index)
            {
                var track = project.Tracks[index]; var top = Ruler + index * Row;
                var divider = new Line { X1 = 0, X2 = Width, Y1 = top + Row, Y2 = top + Row, Stroke = new SolidColorBrush(Color.FromRgb(41, 43, 45)), IsHitTestVisible = false };
                Children.Add(divider);
                var header = new Grid { Width = Header - 1, Height = Row - 1, Background = new SolidColorBrush(Color.FromRgb(52, 55, 58)) };
                header.Children.Add(new Border { Background = new SolidColorBrush(TrackColors[index % TrackColors.Length]), Width = 13, HorizontalAlignment = HorizontalAlignment.Left });
                var name = new Button { Content = track.Name, HorizontalContentAlignment = HorizontalAlignment.Left, FontSize = 11, Width = Header - 33, Height = 25, Padding = new Thickness(3),
                    Margin = new Thickness(21, 2, 3, 0), HorizontalAlignment = HorizontalAlignment.Left, VerticalAlignment = VerticalAlignment.Top, Background = Brushes.Transparent, BorderBrush = Brushes.Transparent };
                name.Click += (_, _) => TrackSelected?.Invoke(track.Id); header.Children.Add(name);
                var flags = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(23, 32, 0, 0), VerticalAlignment = VerticalAlignment.Top };
                var mute = new CheckBox { Content = "M", IsChecked = track.IsMuted, Padding = new Thickness(4, 1, 4, 1), MinWidth = 25, Margin = new Thickness(1), ToolTip = "Mute " + track.Name };
                var solo = new CheckBox { Content = "S", IsChecked = track.IsSolo, Padding = new Thickness(4, 1, 4, 1), MinWidth = 25, Margin = new Thickness(1), ToolTip = "Solo " + track.Name };
                AutomationProperties.SetName(mute, "Mute " + track.Name); AutomationProperties.SetName(solo, "Solo " + track.Name);
                mute.Click += (_, _) => TrackFlagChanged?.Invoke(track.Id, false); solo.Click += (_, _) => TrackFlagChanged?.Invoke(track.Id, true);
                flags.Children.Add(mute); flags.Children.Add(solo); flags.Children.Add(new TextBlock { Text = $" {track.Clips.Length} clips", Foreground = Brushes.Silver, VerticalAlignment = VerticalAlignment.Center, FontSize = 9 });
                header.Children.Add(flags); SetLeft(header, 0); SetTop(header, top); Children.Add(header);
                foreach (var clip in track.Clips)
                {
                    var color = TrackColors[index % TrackColors.Length];
                    var content = new Grid { IsHitTestVisible = false };
                    content.RowDefinitions.Add(new RowDefinition { Height = new GridLength(20) });
                    content.RowDefinitions.Add(new RowDefinition());
                    content.Children.Add(new TextBlock { Text = clip.Name, Foreground = Brushes.Black, TextTrimming = TextTrimming.CharacterEllipsis, Margin = new Thickness(6, 2, 4, 0), FontSize = 11 });
                    var waveform = new WaveformVisual();
                    waveform.SetPeaks(peaks.TryGetValue(clip.Id, out var data) ? data : []);
                    Grid.SetRow(waveform, 1); content.Children.Add(waveform); waveformViews[clip.Id] = waveform;
                    var button = new Button
                    {
                        Content = content,
                        Width = Math.Max(16, clip.Duration * pixels), Height = Row - 10, Padding = new Thickness(0),
                        Margin = new Thickness(0), HorizontalContentAlignment = HorizontalAlignment.Stretch, VerticalContentAlignment = VerticalAlignment.Stretch,
                        Background = new SolidColorBrush(color), Foreground = Brushes.Black,
                        BorderThickness = new Thickness(1),
                        BorderBrush = clip.Id == selected ? Brushes.White : new SolidColorBrush(Color.FromRgb(51, 59, 37)),
                        Opacity = track.IsMuted ? 0.45 : 1,
                        ToolTip = $"{clip.Name} · {clip.Position:0.###}s · {clip.Duration:0.###}s. Drag to move; drag the right edge to trim."
                    };
                    AutomationProperties.SetName(button, $"{track.Name}, {clip.Name}, starts {clip.Position:0.###} seconds, duration {clip.Duration:0.###} seconds");
                    SetLeft(button, Header + clip.Position * pixels); SetTop(button, top + 5); Children.Add(button);
                    Point start = default; bool dragging = false, trim = false;
                    button.PreviewMouseLeftButtonDown += (_, e) =>
                    {
                        start = e.GetPosition(this); trim = e.GetPosition(button).X > button.ActualWidth - 10;
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
        Children.Add(playhead); SetPosition(currentPosition);
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
