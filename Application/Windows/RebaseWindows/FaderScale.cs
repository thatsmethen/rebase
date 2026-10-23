using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Media;

namespace Rebase.Windows;

// The displayed ticks follow the actual WPF value/track geometry. This is the
// application's existing linear-dB control, not an inferred reference taper.
internal sealed class FaderScale : FrameworkElement
{
    private readonly Slider slider;
    private (double Top, double Travel, bool Reversed)? lastGeometry;
    private static readonly double[] Values = [24, 0, -24, -48, -72, -96];
    internal FaderScale(Slider slider)
    {
        this.slider = slider;
        slider.LayoutUpdated += (_, _) =>
        {
            var next = Geometry();
            if (next != lastGeometry) { lastGeometry = next; InvalidateVisual(); }
        };
    }
    private (double Top, double Travel, bool Reversed)? Geometry()
    {
        if (slider.Template?.FindName("PART_Track", slider) is not Track { Thumb: { } thumb } track ||
            track.ActualHeight <= 0 || thumb.ActualHeight <= 0 || !IsLoaded) return null;
        var origin = track.TranslatePoint(new Point(0, thumb.ActualHeight / 2), this);
        return (origin.Y, Math.Max(0, track.ActualHeight - thumb.ActualHeight), track.IsDirectionReversed);
    }
    internal double? TickY(double value)
    {
        if (Geometry() is not { } geometry || slider.Maximum <= slider.Minimum) return null;
        var fraction = (value - slider.Minimum) / (slider.Maximum - slider.Minimum);
        return geometry.Top + geometry.Travel * (geometry.Reversed ? fraction : 1 - fraction);
    }
    protected override void OnRender(DrawingContext drawingContext)
    {
        base.OnRender(drawingContext);
        var ink = new SolidColorBrush(Color.FromRgb(157, 164, 170));
        var pen = new Pen(ink, 0.7);
        foreach (var value in Values)
        {
            if (value < slider.Minimum || value > slider.Maximum || TickY(value) is not { } y) continue;
            drawingContext.DrawLine(pen, new Point(0, y), new Point(4, y));
            var label = new FormattedText(value > 0 ? "+" + value : value.ToString(CultureInfo.InvariantCulture),
                CultureInfo.InvariantCulture, FlowDirection.LeftToRight, new Typeface("Segoe UI"), 8, ink,
                VisualTreeHelper.GetDpi(this).PixelsPerDip);
            drawingContext.DrawText(label, new Point(7, y - label.Height / 2));
        }
    }
}
