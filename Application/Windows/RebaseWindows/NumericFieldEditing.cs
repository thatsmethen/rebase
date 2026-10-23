using System.Globalization;
using System.Windows.Controls;
using System.Windows.Input;

namespace Rebase.Windows;

public partial class MainWindow
{
    private async void NumericFieldKeyDown(object sender, KeyEventArgs e)
    {
        if (sender is not TextBox field || e.Key is not (Key.Enter or Key.Escape)) return;
        e.Handled = true;
        if (model.Busy || !field.IsEnabled) return;
        if (e.Key == Key.Escape)
        {
            RestoreNumericField(field);
            field.SelectAll();
            return;
        }

        // Use the same commands and numeric parser as the visible commit
        // buttons. Text entry alone never mutates the project or history.
        var selectedClip = model.SelectedClip?.Id;
        await Guard(async () =>
        {
            if (field == MoveBox && selectedClip is not null)
                await model.Command("moveClip", clipID: selectedClip, value: Number(field));
            else if (field == TrimBox && selectedClip is not null)
                await model.Command("trimClip", clipID: selectedClip, value: Number(field));
            else if (field == TempoBox)
                await model.Command("setTempo", value: Number(field));
            else if (field == PositionBox)
                await model.Seek(Number(field));
        });
        if (field.IsEnabled && !model.Busy &&
            ((field != MoveBox && field != TrimBox) || selectedClip == model.SelectedClip?.Id))
        {
            field.Focus();
            field.SelectAll();
        }
    }

    private void RestoreNumericField(TextBox field)
    {
        double value;
        string format;
        if (field == MoveBox) { value = model.SelectedClip?.Position ?? 0; format = "0.######"; }
        else if (field == TrimBox) { value = (model.SelectedClip?.Position ?? 0) + (model.SelectedClip?.Duration ?? 0); format = "0.######"; }
        else if (field == TempoBox) { value = model.Project?.Tempo ?? 120; format = "0.###"; }
        else if (field == PositionBox) { value = model.Position; format = "0.000"; }
        else return;
        field.Text = value.ToString(format, CultureInfo.CurrentCulture);
    }
}
