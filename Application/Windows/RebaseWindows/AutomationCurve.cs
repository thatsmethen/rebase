using System.Globalization;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;

namespace Rebase.Windows;

/// Display coordinates only. Evaluation and audio remain owned by RebaseCore.
public sealed class AutomationCurve : FrameworkElement
{
    private AutomationLaneView? lane;
    private double manual, duration = 1;
    private string parameter = "gainDB";
    private string? selected;
    public event Action<double, double>? InsertRequested;
    internal bool DisplayAvailable => (lane?.Points.Count ?? 0) <= 16384;
    internal Rect Plot => new(48, 12, Math.Max(1, ActualWidth - 62), Math.Max(1, ActualHeight - 40));
    internal double Duration => duration;
    internal AutomationLaneView? Lane => lane;
    internal double Minimum => parameter == "gainDB" ? -96 : -1;
    internal double Maximum => parameter == "gainDB" ? 24 : 1;
    internal Point PointPosition(AutomationPointView point) => new(Plot.X + point.Time / duration * Plot.Width, Plot.Bottom - (point.Value - Minimum) / (Maximum - Minimum) * Plot.Height);
    internal IReadOnlyList<Point> Vertices
    {
        get
        {
            if (lane is not { Points.Count: > 0 }) return [PointPosition(new("", 0, manual, "linear")), PointPosition(new("", duration, manual, "linear"))];
            var result = new List<Point> { PointPosition(lane.Points[0] with { Time = 0 }) };
            for (int i = 0; i < lane.Points.Count; i++)
            {
                var point = lane.Points[i];
                if (i > 0 && lane.Points[i - 1].Interpolation == "step") result.Add(PointPosition(point with { Value = lane.Points[i - 1].Value }));
                result.Add(PointPosition(point));
            }
            result.Add(PointPosition(lane.Points[^1] with { Time = duration }));
            return result;
        }
    }
    public void Set(AutomationLaneView? value, string parameterName, double fallback, double projectDuration, string? selectedID)
    {
        lane = value; parameter = parameterName; manual = fallback; selected = selectedID;
        duration = Math.Min(86400, Math.Max(1, Math.Max(projectDuration, lane?.Points.LastOrDefault()?.Time ?? 0)));
        InvalidateVisual();
    }
    public AutomationCurve()
    {
        MinHeight = 120; Focusable = true; Cursor = Cursors.Cross;
        MouseLeftButtonDown += (_, e) =>
        {
            if (!IsEnabled) return;
            e.Handled = InsertAt(e.GetPosition(this));
        };
    }
    internal bool InsertAt(Point point)
    {
        if (!IsEnabled || !DisplayAvailable || !Plot.Contains(point)) return false;
        Focus();
        InsertRequested?.Invoke(Math.Clamp((point.X - Plot.X) / Plot.Width * duration, 0, 86400),
            Math.Clamp(Maximum - (point.Y - Plot.Y) / Plot.Height * (Maximum - Minimum), Minimum, Maximum));
        return true;
    }
    protected override void OnRender(DrawingContext drawing)
    {
        base.OnRender(drawing);
        drawing.DrawRectangle(new SolidColorBrush(Color.FromRgb(30, 33, 36)), null, new Rect(0, 0, ActualWidth, ActualHeight));
        var thin = new Pen(new SolidColorBrush(Color.FromRgb(61, 67, 73)), 1);
        void Label(string text, Point at) => drawing.DrawText(new FormattedText(text, CultureInfo.CurrentCulture, FlowDirection.LeftToRight,
            new Typeface("Segoe UI"), 10, Brushes.LightGray, VisualTreeHelper.GetDpi(this).PixelsPerDip), at);
        for (int i = 0; i <= 4; i++)
        {
            var y = Plot.Top + Plot.Height * i / 4;
            drawing.DrawLine(thin, new Point(Plot.Left, y), new Point(Plot.Right, y));
            Label((Maximum - (Maximum - Minimum) * i / 4).ToString("0.##", CultureInfo.CurrentCulture), new Point(4, y - 6));
            var x = Plot.Left + Plot.Width * i / 4;
            drawing.DrawLine(thin, new Point(x, Plot.Top), new Point(x, Plot.Bottom));
            Label((duration * i / 4).ToString("0.##", CultureInfo.CurrentCulture) + " s", new Point(Math.Min(x, Plot.Right - 36), Plot.Bottom + 7));
        }
        if (!DisplayAvailable)
        {
            Label("Curve drawing unavailable above 16,384 points; all points remain in the list.", new Point(Plot.Left + 5, Plot.Top + 12));
            return;
        }
        var vertices = Vertices;
        var curvePen = new Pen(lane?.IsReadEnabled == false ? Brushes.SlateGray : new SolidColorBrush(Color.FromRgb(103, 207, 223)), 1.5);
        for (int i = 1; i < vertices.Count; i++) drawing.DrawLine(curvePen, vertices[i - 1], vertices[i]);
        if (lane?.IsReadEnabled == false)
        {
            var manualY = PointPosition(new("", 0, manual, "linear")).Y;
            drawing.DrawLine(new Pen(Brushes.LightGray, 1) { DashStyle = DashStyles.Dash }, new Point(Plot.Left, manualY), new Point(Plot.Right, manualY));
        }
        foreach (var point in lane?.Points ?? [])
            drawing.DrawEllipse(point.Id == selected ? Brushes.White : curvePen.Brush, new Pen(Brushes.Black, 1), PointPosition(point), 3.5, 3.5);
        if (IsKeyboardFocused) drawing.DrawRectangle(null, new Pen(Brushes.LightBlue, 1), new Rect(0.5, 0.5, Math.Max(0, ActualWidth - 1), Math.Max(0, ActualHeight - 1)));
    }
}
