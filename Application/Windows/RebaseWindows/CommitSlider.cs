using System.Windows;
using System.Windows.Automation;
using System.Windows.Automation.Peers;
using System.Windows.Automation.Provider;
using System.Windows.Controls;
using System.Windows.Input;

namespace Rebase.Windows;

// Drag/keyboard previews stay local until the gesture completes. Assistive
// technology RangeValue edits use that same commit boundary instead of merely
// moving the thumb without changing the shared project.
public sealed class CommitSlider : Slider
{
    public event EventHandler? ValueCommitted;
    internal void Commit() { if (IsEnabled) ValueCommitted?.Invoke(this, EventArgs.Empty); }
    protected override void OnPreviewMouseLeftButtonUp(MouseButtonEventArgs e)
    {
        base.OnPreviewMouseLeftButtonUp(e);
        Commit();
    }
    protected override void OnKeyUp(KeyEventArgs e)
    {
        base.OnKeyUp(e);
        if (e.Key is Key.Left or Key.Right or Key.Up or Key.Down or Key.Home or Key.End or Key.PageUp or Key.PageDown) Commit();
    }
    protected override AutomationPeer OnCreateAutomationPeer() => new CommitSliderAutomationPeer(this);

    private sealed class CommitSliderAutomationPeer(CommitSlider slider) : SliderAutomationPeer(slider), IRangeValueProvider
    {
        public override object GetPattern(PatternInterface patternInterface) => patternInterface == PatternInterface.RangeValue ? this : base.GetPattern(patternInterface);
        bool IRangeValueProvider.IsReadOnly => !slider.IsEnabled;
        double IRangeValueProvider.LargeChange => slider.LargeChange;
        double IRangeValueProvider.SmallChange => slider.SmallChange;
        double IRangeValueProvider.Maximum => slider.Maximum;
        double IRangeValueProvider.Minimum => slider.Minimum;
        double IRangeValueProvider.Value => slider.Value;
        void IRangeValueProvider.SetValue(double value)
        {
            if (!slider.IsEnabled) throw new ElementNotEnabledException();
            if (!double.IsFinite(value) || value < slider.Minimum || value > slider.Maximum) throw new ArgumentOutOfRangeException(nameof(value));
            slider.SetCurrentValue(ValueProperty, value);
            slider.Commit();
        }
    }
}
