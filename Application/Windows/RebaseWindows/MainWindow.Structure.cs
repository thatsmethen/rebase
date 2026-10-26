using System.Windows;

namespace Rebase.Windows;

public partial class MainWindow
{
    private bool openingProjectStructure;
    private ProjectStructureWindow? activeProjectStructure;
    private async void ShowProjectStructure(object sender, RoutedEventArgs e) => await ShowProjectStructure();
    internal async Task ShowProjectStructure()
    {
        if (closing || openingProjectStructure || reviewingCPR || openingAutomation || openingSourceAudio || documentOperation || model.Project is null) return;
        openingProjectStructure = true; IsEnabled = false;
        try
        {
            await model.SuspendAndDrain(); model.ResumeInput();
            var snapshot = await model.InspectProjectStructure();
            if (snapshot is null) return;
            // The complete immutable report owns no live helper token. Keep the
            // owner disabled until the view closes, without mutating playback.
            await model.SuspendAndDrain();
            activeProjectStructure = new ProjectStructureWindow(snapshot) { Owner = this };
            activeProjectStructure.Show(); await activeProjectStructure.Completion;
        }
        catch (Exception error) { model.Report(error); }
        finally { activeProjectStructure = null; openingProjectStructure = false; model.ResumeInput(); IsEnabled = true; Activate(); }
    }
}
