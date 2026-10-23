using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Shapes;

namespace Rebase.Windows;

public sealed class TimelineView : Canvas
{
    private const double Header = 190, Row = 76, Ruler = 34;
    private static readonly Brush[] Colors = [new SolidColorBrush(Color.FromRgb(102, 187, 160)), new SolidColorBrush(Color.FromRgb(214, 170, 101)), new SolidColorBrush(Color.FromRgb(145, 154, 219)), new SolidColorBrush(Color.FromRgb(211, 133, 165))];
    private readonly Line playhead = new() { Stroke = Brushes.White, StrokeThickness = 1.5, IsHitTestVisible = false };
    private ProjectView? project;
    private string? selected;
    private double pixels = 40;
    public event Action<string>? ClipSelected;
    public event Action<string, double, bool>? ClipDragged;
    public event Action<double>? SeekRequested;
    public TimelineView() { Background = new SolidColorBrush(Color.FromRgb(23, 28, 35)); ClipToBounds = true; MouseLeftButtonDown += EmptyClick; }
    public void SetProject(ProjectView? value, string? selectedID, double pixelsPerSecond)
    {
        project = value; selected = selectedID; pixels = pixelsPerSecond; Rebuild();
    }
    public void SetPosition(double seconds)
    {
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
        var duration = Math.Max(24, project?.Duration ?? 24);
        Width = Header + duration * pixels + 100;
        Height = Ruler + Math.Max(4, project?.Tracks.Length ?? 0) * Row;
        var tickStep = Math.Max(1, Math.Ceiling(duration / 150));
        for (double t = 0; t <= duration; t += tickStep)
        {
            var x = Header + t * pixels;
            var line = new Line { X1 = x, X2 = x, Y1 = Ruler, Y2 = Height, Stroke = new SolidColorBrush(Color.FromRgb(49, 57, 69)), IsHitTestVisible = false };
            Children.Add(line);
            var label = new TextBlock { Text = t.ToString("0.##", System.Globalization.CultureInfo.InvariantCulture) + "s", Foreground = Brushes.LightSlateGray, FontSize = 11, IsHitTestVisible = false };
            SetLeft(label, x + 4); SetTop(label, 8); Children.Add(label);
        }
        if (project is not null)
        {
            for (var index = 0; index < project.Tracks.Length; ++index)
            {
                var track = project.Tracks[index]; var top = Ruler + index * Row;
                var divider = new Line { X1 = 0, X2 = Width, Y1 = top + Row, Y2 = top + Row, Stroke = new SolidColorBrush(Color.FromRgb(64, 71, 83)), IsHitTestVisible = false };
                Children.Add(divider);
                var name = new TextBlock { Text = track.Name + (track.IsMuted ? "  [M]" : "") + (track.IsSolo ? "  [S]" : ""), Foreground = Brushes.White, FontWeight = FontWeights.SemiBold, Width = Header - 22, TextTrimming = TextTrimming.CharacterEllipsis, IsHitTestVisible = false };
                SetLeft(name, 14); SetTop(name, top + 25); Children.Add(name);
                foreach (var clip in track.Clips)
                {
                    var button = new Button
                    {
                        Content = new TextBlock { Text = clip.Name, TextTrimming = TextTrimming.CharacterEllipsis },
                        Width = Math.Max(16, clip.Duration * pixels), Height = Row - 18, Padding = new Thickness(9, 4, 12, 4),
                        Margin = new Thickness(0), HorizontalContentAlignment = HorizontalAlignment.Left,
                        Background = Colors[index % Colors.Length], Foreground = Brushes.Black,
                        BorderThickness = new Thickness(clip.Id == selected ? 3 : 1),
                        BorderBrush = clip.Id == selected ? Brushes.White : Brushes.Transparent,
                        Opacity = track.IsMuted ? 0.45 : 1,
                        ToolTip = $"{clip.Name} · {clip.Position:0.###}s · {clip.Duration:0.###}s. Drag to move; drag the right edge to trim."
                    };
                    AutomationProperties.SetName(button, $"{track.Name}, {clip.Name}, starts {clip.Position:0.###} seconds, duration {clip.Duration:0.###} seconds");
                    SetLeft(button, Header + clip.Position * pixels); SetTop(button, top + 9); Children.Add(button);
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
        Children.Add(playhead); SetPosition(0);
    }
}
