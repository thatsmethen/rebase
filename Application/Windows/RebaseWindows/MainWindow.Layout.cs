using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Threading;

namespace Rebase.Windows;

public partial class MainWindow
{
    private bool workspaceReady, changingWorkspace;
    private bool leftZoneVisible = true, mixerZoneVisible = true;
    // Reserve enough arrangement height for four normal rows at MinHeight.
    // The user can still enlarge the mixer and scroll the arrangement.
    private double savedMixerHeight = 216, mixerFaderHeight = 110;
    private string? lastExpandedSourceID;
    private bool LayoutCaptureActive => Timeline.IsMouseCaptureWithin || Mixer.IsMouseCaptureWithin || SelectedChannel.IsMouseCaptureWithin || EditSurface.IsMouseCaptureWithin || MixerSplitter.IsMouseCaptureWithin;

    private void InitializeWorkspaceLayout()
    {
        workspaceReady = true;
        Timeline.SetRowHeight(44);
        ApplyWorkspacePanes();
    }

    private void RowDensityChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!workspaceReady || changingWorkspace) return;
        var height = RowDensityBox.SelectedIndex == 1 ? 68 : 44;
        if (height == Timeline.RowHeight) return;
        if (LayoutCaptureActive)
        {
            changingWorkspace = true;
            try { RowDensityBox.SelectedIndex = Timeline.RowHeight == 44 ? 0 : 1; }
            finally { changingWorkspace = false; }
            return;
        }
        Timeline.SetRowHeight(height);
        Timeline.SetHorizontalOffset(TimelineScroll.HorizontalOffset);
    }

    private void WorkspacePaneChanged(object sender, RoutedEventArgs e)
    {
        if (!workspaceReady || changingWorkspace) return;
        if (LayoutCaptureActive)
        {
            changingWorkspace = true;
            try { LeftZoneToggle.IsChecked = leftZoneVisible; MixerZoneToggle.IsChecked = mixerZoneVisible; }
            finally { changingWorkspace = false; }
            return;
        }
        if (MixerZoneToggle.IsChecked is not true && mixerZoneVisible) savedMixerHeight = MixerRow.ActualHeight;
        if (LeftZoneToggle.IsChecked is not true && (EditSurface.IsKeyboardFocusWithin || ChannelSurface.IsKeyboardFocusWithin)) LeftZoneToggle.Focus();
        if (MixerZoneToggle.IsChecked is not true && (MixerZone.IsKeyboardFocusWithin || MixerSplitter.IsKeyboardFocused)) MixerZoneToggle.Focus();
        leftZoneVisible = LeftZoneToggle.IsChecked is true;
        mixerZoneVisible = MixerZoneToggle.IsChecked is true;
        ApplyWorkspacePanes();
    }

    private void ApplyWorkspacePanes()
    {
        ChannelColumn.Width = new GridLength(leftZoneVisible ? 104 : 0);
        InspectorColumn.Width = new GridLength(leftZoneVisible ? 182 : 0);
        ChannelSurface.Visibility = EditSurface.Visibility = leftZoneVisible ? Visibility.Visible : Visibility.Collapsed;
        MixerZone.Visibility = MixerSplitter.Visibility = mixerZoneVisible ? Visibility.Visible : Visibility.Collapsed;
        MixerDividerRow.Height = new GridLength(mixerZoneVisible ? 5 : 0);
        ArrangementRow.Height = new GridLength(1, GridUnitType.Star);
        MixerRow.MinHeight = 0;
        MixerRow.MaxHeight = mixerZoneVisible ? MaximumMixerHeight() : 0;
        MixerRow.MinHeight = mixerZoneVisible ? 196 : 0;
        MixerRow.Height = new GridLength(mixerZoneVisible ? Math.Clamp(savedMixerHeight, 196, MixerRow.MaxHeight) : 0);
    }

    private double MaximumMixerHeight() => ArrangementWorkspace.ActualHeight <= 0 ? 376 : Math.Max(196, Math.Min(376, ArrangementWorkspace.ActualHeight - 225));
    private void WorkspaceSizeChanged(object sender, SizeChangedEventArgs e)
    {
        if (!workspaceReady || !mixerZoneVisible) return;
        MixerRow.MaxHeight = MaximumMixerHeight();
        if (MixerRow.Height.IsAbsolute && MixerRow.Height.Value > MixerRow.MaxHeight) MixerRow.Height = new GridLength(MixerRow.MaxHeight);
    }

    private void MixerSplitterDragged(object sender, DragDeltaEventArgs e)
    {
        // GridSplitter owns the actual row resize. This value only restores the
        // last visible size after hiding the lower zone.
        if (workspaceReady && mixerZoneVisible) savedMixerHeight = MixerRow.ActualHeight;
    }

    private void MixerViewportChanged(object sender, SizeChangedEventArgs e)
    {
        if (!workspaceReady || !mixerZoneVisible || e.NewSize.Height <= 0) return;
        var height = Math.Clamp(e.NewSize.Height - 111, 60, 240);
        if (Math.Abs(height - mixerFaderHeight) < 0.5) return;
        mixerFaderHeight = height;
        RefreshMixer();
        RestoreMixerFocus();
    }

    private void RestoreMixerFocus()
    {
        if (model.Busy || mixerFocus is not { } key) return;
        Control? restore = mixerSliders.GetValueOrDefault(key) ?? (Control?)mixerValues.GetValueOrDefault(key);
        mixerFocus = null;
        if (restore is not null) Dispatcher.BeginInvoke(() => { if (restore.IsVisible && restore.IsEnabled) restore.Focus(); }, DispatcherPriority.Input);
    }

    private void RefreshEditingAvailability()
    {
        var editable = !model.Busy && model.SelectedClip is not null;
        ClipInspector.IsEnabled = editable;
        SplitToolbarButton.IsEnabled = DeleteToolbarButton.IsEnabled = editable;
        SplitInspectorButton.IsEnabled = DeleteInspectorButton.IsEnabled = editable;
        SplitMenuItem.IsEnabled = DeleteMenuItem.IsEnabled = editable;
        var sourceID = model.SelectedSourceEvent?.Id;
        if (sourceID is not null && sourceID != lastExpandedSourceID) SourceSection.IsExpanded = true;
        lastExpandedSourceID = sourceID;
    }
}
