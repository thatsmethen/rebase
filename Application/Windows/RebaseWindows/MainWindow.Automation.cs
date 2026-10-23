using System.Windows;

namespace Rebase.Windows;

public partial class MainWindow
{
    private AutomationEditorWindow? activeAutomationEditor;
    private bool openingAutomation;
    private async void ShowAutomation(object sender, RoutedEventArgs e)
    {
        if (openingAutomation || reviewingCPR || closing) return;
        openingAutomation = true; IsEnabled = false;
        try
        {
            await model.SuspendAndDrain(); model.ResumeInput();
            if (model.SelectedTrack is not { } track) { model.Report(new InvalidOperationException("Select a track before editing automation.")); return; }
            activeAutomationEditor = new AutomationEditorWindow(model, track.Id) { Owner = this };
            activeAutomationEditor.Show();
            await activeAutomationEditor.Completion;
        }
        catch (Exception error) { model.Report(error); }
        finally { activeAutomationEditor = null; openingAutomation = false; model.ResumeInput(); IsEnabled = true; Activate(); }
    }
}
