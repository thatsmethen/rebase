using Microsoft.Win32;
using System.Windows;

namespace Rebase.Windows;

public partial class MainWindow
{
    private bool documentOperation;
    private Func<MessageBoxResult>? smokeNewProjectDecision;
    private Func<string[]?>? smokeAudioPaths;
    private Func<string?>? smokeDocumentSaveDestination;

    private async void NewProject(object sender, RoutedEventArgs e) => await CreateNewProject();
    private async Task CreateNewProject()
    {
        if (documentOperation || closing || reviewingCPR || openingAutomation || openingSourceAudio) return;
        documentOperation = true; IsEnabled = false;
        try
        {
            await model.SuspendAndDrain(cancelSourcePreparation: true);
            model.ResumeInput();
            var discard = false;
            if (model.NeedsSaveDecision)
            {
                var answer = smokeNewProjectDecision?.Invoke() ?? MessageBox.Show(this,
                    "Save changes before creating a new project?\nYes: Save · No: Discard · Cancel: Keep this project",
                    "Unsaved changes", MessageBoxButton.YesNoCancel, MessageBoxImage.Question);
                if (answer == MessageBoxResult.Cancel) return;
                if (answer == MessageBoxResult.Yes && !await Save()) return;
                discard = answer == MessageBoxResult.No;
            }
            await model.NewProject(discard);
        }
        catch (Exception error) { model.Report(error); }
        finally { model.ResumeInput(); documentOperation = false; IsEnabled = true; Activate(); }
    }

    private async void ImportAudio(object sender, RoutedEventArgs e) => await SelectAudioToImport();
    private async Task SelectAudioToImport()
    {
        if (documentOperation || closing || model.Project is null || reviewingCPR || openingAutomation || openingSourceAudio) return;
        documentOperation = true; IsEnabled = false;
        try
        {
            await model.SuspendAndDrain(cancelSourcePreparation: true);
            model.ResumeInput();
            string[]? paths;
            if (smokeAudioPaths is not null) paths = smokeAudioPaths();
            else
            {
                var picker = new OpenFileDialog { Title = "Import mono or stereo PCM WAV audio as new tracks",
                    Filter = "PCM WAV audio|*.wav;*.wave", CheckFileExists = true, Multiselect = true };
                paths = picker.ShowDialog(this) == true ? picker.FileNames : null;
            }
            if (paths is null) return;
            await model.ImportAudio(paths);
        }
        catch (Exception error) { model.Report(error); }
        finally { model.ResumeInput(); documentOperation = false; IsEnabled = true; Activate(); }
    }
}
