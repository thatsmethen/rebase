using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace Rebase.Windows;

public partial class MainWindow
{
    // These helpers inspect the completed native layout. They never arrange,
    // focus, enable, select, or otherwise repair the controls being measured.
    private sealed record TopRowsElement(
        string name, double x, double y, double width, double height, bool visible,
        string? text, string? tooltip, double? text_natural_width, double? text_natural_height,
        double? text_content_width, double? text_content_height,
        bool? text_fits_width, bool? text_fits_height, string? text_trimming);

    private object MeasureTopRowsLayout()
    {
        if (Content is not FrameworkElement client || !client.IsVisible ||
            !double.IsFinite(client.ActualWidth) || !double.IsFinite(client.ActualHeight) ||
            client.ActualWidth <= 0 || client.ActualHeight <= 0)
            throw new InvalidOperationException("Top-row measurement requires a visible client root.");

        TopRowsElement Measure(FrameworkElement element, string? name = null)
        {
            var visible = element.IsVisible;
            var bounds = visible
                ? element.TransformToAncestor(client).TransformBounds(new Rect(element.RenderSize))
                : new Rect(0, 0, 0, 0);
            if (new[] { bounds.X, bounds.Y, bounds.Width, bounds.Height }.Any(value => !double.IsFinite(value)) ||
                (visible && (bounds.Width <= 0 || bounds.Height <= 0)))
                throw new InvalidOperationException("A measured top-row element has invalid bounds: " + (name ?? element.Name));

            string? text = null, trimming = null;
            double? naturalWidth = null, naturalHeight = null, contentWidth = null, contentHeight = null;
            bool? fitsWidth = null, fitsHeight = null;
            var tooltip = element.ToolTip as string;
            if (element is TextBlock block)
            {
                text = block.Text; trimming = block.TextTrimming.ToString();
                contentWidth = Math.Max(0, block.ActualWidth - block.Padding.Left - block.Padding.Right);
                contentHeight = Math.Max(0, block.ActualHeight - block.Padding.Top - block.Padding.Bottom);
                var measured = new FormattedText(text, CultureInfo.CurrentCulture, block.FlowDirection,
                    new Typeface(block.FontFamily, block.FontStyle, block.FontWeight, block.FontStretch),
                    block.FontSize, Brushes.White, VisualTreeHelper.GetDpi(block).PixelsPerDip);
                naturalWidth = measured.WidthIncludingTrailingWhitespace; naturalHeight = measured.Height;
            }
            else if (element is TextBox box)
            {
                text = box.Text; trimming = "None";
                if (visible && box.Template.FindName("PART_ContentHost", box) is not FrameworkElement)
                    throw new InvalidOperationException("A numeric field has no rendered content host: " + box.Name);
                if (box.Template.FindName("PART_ContentHost", box) is FrameworkElement host)
                {
                    contentWidth = host is ScrollViewer scroll ? scroll.ViewportWidth : host.ActualWidth;
                    contentHeight = host is ScrollViewer scrollHeight ? scrollHeight.ViewportHeight : host.ActualHeight;
                    if (visible)
                    {
                        var inner = host.TransformToAncestor(client).TransformBounds(new Rect(host.RenderSize));
                        if (!Contains(bounds, inner))
                            throw new InvalidOperationException("A numeric content host extends outside its field: " + box.Name);
                    }
                }
                var measured = new FormattedText(text, CultureInfo.CurrentCulture, box.FlowDirection,
                    new Typeface(box.FontFamily, box.FontStyle, box.FontWeight, box.FontStretch),
                    box.FontSize, Brushes.White, VisualTreeHelper.GetDpi(box).PixelsPerDip);
                naturalWidth = measured.WidthIncludingTrailingWhitespace; naturalHeight = measured.Height;
            }
            if (text is not null)
            {
                if (naturalWidth is not { } nw || naturalHeight is not { } nh ||
                    contentWidth is not { } cw || contentHeight is not { } ch ||
                    new[] { nw, nh, cw, ch }.Any(value => !double.IsFinite(value) || value < 0))
                    throw new InvalidOperationException("A top-row text measurement is unavailable: " + (name ?? element.Name));
                fitsWidth = nw <= cw + 0.5; fitsHeight = nh <= ch + 0.5;
                if (visible && (text.Length == 0 || cw <= 0 || ch <= 0 || fitsHeight != true ||
                    (fitsWidth != true && !(element is TextBlock && trimming != "None" && tooltip == text))))
                    throw new InvalidOperationException("Top-row text is clipped without an accessible full value: " + (name ?? element.Name));
            }
            return new(name ?? element.Name, bounds.X, bounds.Y, bounds.Width, bounds.Height, visible,
                text, tooltip, naturalWidth, naturalHeight, contentWidth, contentHeight, fitsWidth, fitsHeight, trimming);
        }

        static Rect Box(TopRowsElement element) => new(element.x, element.y, element.width, element.height);
        static bool Contains(Rect outer, Rect inner) => inner.Left >= outer.Left - 0.5 && inner.Top >= outer.Top - 0.5 &&
            inner.Right <= outer.Right + 0.5 && inner.Bottom <= outer.Bottom + 0.5;
        static void Contained(IEnumerable<TopRowsElement> elements, TopRowsElement parent)
        {
            foreach (var element in elements.Where(item => item.visible))
                if (!Contains(Box(parent), Box(element)))
                    throw new InvalidOperationException("Top-row element extends beyond its region: " + element.name);
        }
        static void Disjoint(IReadOnlyList<TopRowsElement> elements)
        {
            for (var first = 0; first < elements.Count; first++)
                for (var second = first + 1; second < elements.Count; second++)
                {
                    if (!elements[first].visible || !elements[second].visible) continue;
                    var intersection = Rect.Intersect(Box(elements[first]), Box(elements[second]));
                    if (!intersection.IsEmpty && intersection.Width > 0.5 && intersection.Height > 0.5)
                        throw new InvalidOperationException("Top-row sibling controls overlap: " + elements[first].name + " / " + elements[second].name);
                }
        }

        var bands = new[] { MenuBand, (FrameworkElement)ToolbarBand, ProjectStatusBand, EventInfoBand }.Select(element => Measure(element)).ToArray();
        var expectedHeights = new double[] { 25, 30, 18, 34 };
        var bottom = 0.0;
        for (var index = 0; index < bands.Length; index++)
        {
            var band = bands[index];
            if (!band.visible || Math.Abs(band.x) > 0.5 || Math.Abs(band.y - bottom) > 0.5 ||
                Math.Abs(band.width - client.ActualWidth) > 0.5 || Math.Abs(band.height - expectedHeights[index]) > 0.5)
                throw new InvalidOperationException("Top-row bands do not match the declared contiguous layout: " + band.name);
            bottom += band.height;
        }
        var workspace = Measure(Workspace);
        if (Math.Abs(bottom - 107) > 0.5 || Math.Abs(workspace.y - bottom) > 0.5)
            throw new InvalidOperationException("The workspace does not begin after the 107-DIP top stack.");

        var toolbar = new FrameworkElement[] { ExampleButton, OpenProjectButton, SaveProjectButton, UndoButton, RedoButton,
            SplitToolbarButton, DeleteToolbarButton, SnapBox, Zoom, RulerModeBox, RowDensityBox, LeftZoneToggle, MixerZoneToggle, ExportButton }
            .Select(element => Measure(element)).ToArray();
        if (toolbar.Any(element => !element.visible || element.width < 20 || element.height < (element.name == "Zoom" ? 12 : 24)))
            throw new InvalidOperationException("An existing toolbar control is missing or has a collapsed hit area.");
        Contained(toolbar, bands[1]); Disjoint(toolbar);

        var cells = new[] { EventNameCell, EventStartCell, EventEndCell, EventOffsetCell }.Select(element => Measure(element)).ToArray();
        if (cells.Any(element => !element.visible)) throw new InvalidOperationException("An event-information cell is hidden.");
        Contained(cells, bands[3]); Disjoint(cells);
        var startLabel = EventStartCell.Children.OfType<TextBlock>().Single();
        var endLabel = EventEndCell.Children.OfType<TextBlock>().Single();
        var offsetLabel = EventOffsetCell.Children.OfType<TextBlock>().Single(block => block != SourceOffsetText);
        var eventControls = new[] { Measure(SelectionName), Measure(SelectionKind), Measure(MoveBox), Measure(MoveButton),
            Measure(TrimBox), Measure(TrimButton), Measure(SourceOffsetText), Measure(startLabel, "EventStartLabel"),
            Measure(endLabel, "EventEndLabel"), Measure(offsetLabel, "EventOffsetLabel") };
        if (eventControls.Any(element => !element.visible)) throw new InvalidOperationException("An event-information control is hidden.");
        Contained(eventControls, bands[3]); Disjoint(eventControls);
        Contained(eventControls.Where(element => element.name is "SelectionName" or "SelectionKind"), cells[0]);
        Contained(eventControls.Where(element => element.name is "MoveBox" or "MoveButton" or "EventStartLabel"), cells[1]);
        Contained(eventControls.Where(element => element.name is "TrimBox" or "TrimButton" or "EventEndLabel"), cells[2]);
        Contained(eventControls.Where(element => element.name is "SourceOffsetText" or "EventOffsetLabel"), cells[3]);

        var status = new[] { Measure(ProjectName), Measure(ProjectInfo), Measure(ProjectLimit) };
        if (!status[0].visible || !status[1].visible || (status[2].visible && status[2].text_fits_width != true))
            throw new InvalidOperationException("Project identity or the visible playback limitation is clipped.");
        Contained(status, bands[2]); Disjoint(status);
        return new { stack_height = bottom, bands, toolbar_controls = toolbar, event_cells = cells,
            event_controls = eventControls, status_controls = status, client_width = client.ActualWidth, client_height = client.ActualHeight };
    }

    private object MeasureTimingMarkers(string context)
    {
        if (model.Busy) throw new InvalidOperationException("Timing markers must be observed after the shared command completes.");
        var fields = new Control[] { MoveBox, TrimBox, MoveButton, TrimButton };
        var editing = ClipInspector.IsEnabled && fields.All(field => field.IsEnabled);
        var unavailable = MoveBox.Text == "—" && TrimBox.Text == "—" && SourceOffsetText.Text == "—";
        var limitationVisible = ProjectLimit.IsVisible;
        var needsLimitation = model.Project?.Tracks.Any(track => track.UnresolvedAudioEvents.Length > 0) == true;
        if (limitationVisible != needsLimitation || (limitationVisible && ProjectLimit.Text != "Project playback unavailable"))
            throw new InvalidOperationException("Project playback limitation does not match retained source events.");
        switch (context)
        {
            case "empty":
                if (model.SelectedClip is not null || model.SelectedSourceEvent is not null || model.State.Selection.ClipID is not null ||
                    SelectionName.Text != "No event selected" || SelectionKind.Text != "Event information" || !unavailable ||
                    ClipInspector.IsEnabled || fields.Any(field => field.IsEnabled))
                    throw new InvalidOperationException("Empty selection exposes ordinary timing or editing.");
                break;
            case "source":
                if (model.SelectedClip is not null || model.SelectedSourceEvent is not { } source || SelectionName.Text != source.Name ||
                    SelectionKind.Text != "Retained source event" || !unavailable || !limitationVisible ||
                    ClipInspector.IsEnabled || fields.Any(field => field.IsEnabled))
                    throw new InvalidOperationException("Retained source selection exposes ordinary timing or editing.");
                break;
            case "ordinary":
                if (model.SelectedClip is not { } clip || model.SelectedSourceEvent is not null || !editing ||
                    SelectionName.Text != clip.Name || SelectionKind.Text != "Selected event" ||
                    !double.TryParse(MoveBox.Text, NumberStyles.Float, CultureInfo.CurrentCulture, out var start) ||
                    !double.TryParse(TrimBox.Text, NumberStyles.Float, CultureInfo.CurrentCulture, out var end) ||
                    !SourceOffsetText.Text.EndsWith(" s", StringComparison.Ordinal) ||
                    !double.TryParse(SourceOffsetText.Text[..^2], NumberStyles.Float, CultureInfo.CurrentCulture, out var offset) ||
                    !double.IsFinite(start) || !double.IsFinite(end) || !double.IsFinite(offset) ||
                    Math.Abs(start - clip.Position) > 0.000001 || Math.Abs(end - clip.Position - clip.Duration) > 0.000001 ||
                    Math.Abs(offset - clip.SourceOffset) > 0.000501 || (clip.Position == 0 && start != 0))
                    throw new InvalidOperationException("Ordinary event timing no longer matches the selected clip.");
                break;
            default: throw new ArgumentOutOfRangeException(nameof(context), "Unknown timing-marker context.");
        }
        return new { context, name = SelectionName.Text, kind = SelectionKind.Text, start = MoveBox.Text, end = TrimBox.Text,
            offset = SourceOffsetText.Text, editing_enabled = editing, project_limitation_visible = limitationVisible };
    }
}
