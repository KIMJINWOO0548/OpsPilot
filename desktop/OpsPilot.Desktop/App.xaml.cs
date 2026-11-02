using System.Windows;
namespace OpsPilot.Desktop;
public partial class App : Application
{
    private Mutex? instance;
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        try
        {
            var data = DesktopPolicy.DataDirectory(e.Args);
            for (var directory = new DirectoryInfo(data); directory != null; directory = directory.Parent)
                if (directory.Exists && (directory.Attributes & FileAttributes.ReparsePoint) != 0) throw new ArgumentException();
            Directory.CreateDirectory(data);
            if ((File.GetAttributes(data) & FileAttributes.ReparsePoint) != 0) throw new ArgumentException();
            instance = new Mutex(true, DesktopPolicy.InstanceName(data), out var created);
            if (!created) { MessageBox.Show("같은 데이터 폴더의 OpsPilot-X가 이미 실행 중입니다.", "OpsPilot-X"); Shutdown(); return; }
            MainWindow = new MainWindow(data); MainWindow.Show();
        }
        catch { MessageBox.Show("데이터 경로 또는 실행 구성을 확인하세요.", "OpsPilot-X"); Shutdown(1); }
    }
    protected override void OnExit(ExitEventArgs e) { instance?.Dispose(); base.OnExit(e); }
}
