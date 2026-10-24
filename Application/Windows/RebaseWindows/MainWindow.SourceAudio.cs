using System.Windows;

namespace Rebase.Windows;

public partial class MainWindow
{
    private SourceAudioWindow? activeSourceAudio;
    private bool openingSourceAudio;
    private async void ShowSourceAudio(object sender, RoutedEventArgs e)
    {
        if (openingSourceAudio || openingAutomation || reviewingCPR || closing) return;
        openingSourceAudio = true; IsEnabled = false;
        try
        {
            await model.SuspendAndDrain(); model.ResumeInput();
            await model.InspectSource();
            if (model.SourceInspection is null) return;
            activeSourceAudio = new SourceAudioWindow(model) { Owner = this };
            activeSourceAudio.Show();
            await activeSourceAudio.Completion;
        }
        catch (Exception error) { model.Report(error); }
        finally { activeSourceAudio = null; openingSourceAudio = false; model.ResumeInput(); IsEnabled = true; Activate(); }
    }
}
