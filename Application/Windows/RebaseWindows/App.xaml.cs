using System.Windows;
namespace Rebase.Windows;
public partial class App : Application
{
    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        string? smokePath = null, sourceProject = null, sourceMedia = null;
        if (e.Args.Length != 0)
        {
            if ((e.Args.Length == 3 || e.Args.Length == 7) && e.Args[0] == "--smoke" && e.Args[1] == "--smoke-json" && Path.IsPathFullyQualified(e.Args[2]))
            {
                smokePath = e.Args[2];
                if (e.Args.Length == 7)
                {
                    if (e.Args[3] != "--smoke-source-project" || e.Args[5] != "--smoke-source-media" ||
                        !Path.IsPathFullyQualified(e.Args[4]) || !Path.IsPathFullyQualified(e.Args[6])) { Shutdown(2); return; }
                    sourceProject = e.Args[4]; sourceMedia = e.Args[6];
                }
            }
            else { Shutdown(2); return; }
        }
        if (smokePath is not null) ShutdownMode = ShutdownMode.OnExplicitShutdown;
        var window = new MainWindow(); MainWindow = window; window.Show();
        if (smokePath is not null) Shutdown(await window.RunSmoke(smokePath, sourceProject, sourceMedia));
    }
}
