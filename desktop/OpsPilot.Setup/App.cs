using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using Microsoft.Win32;

namespace OpsPilot.Setup;

public sealed class SetupApp : Application
{
    private static readonly string InstallRoot = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "OpsPilot-X");
    private static string RegistryPath(string version) => @"Software\Microsoft\Windows\CurrentVersion\Uninstall\OpsPilot-X-" + version;

    [STAThread]
    public static void Main(string[] args)
    {
        var app = new SetupApp();
        var version = args.Length == 2 && args[0] == "--uninstall" ? args[1] : null;
        if (args.Length != 0 && version == null) { MessageBox.Show("지원하지 않는 설치 옵션입니다.", "OpsPilot-X"); return; }
        if (version != null)
        {
            try
            {
                var installed = SetupEngine.VersionPath(InstallRoot, version);
                if (Environment.ProcessPath!.StartsWith(installed + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                {
                    var helper = Path.Combine(Path.GetTempPath(), "OpsPilot-X-remove-" + Guid.NewGuid().ToString("N") + ".exe");
                    File.Copy(Environment.ProcessPath!, helper, false);
                    var start = new ProcessStartInfo(helper) { UseShellExecute = false };
                    start.ArgumentList.Add("--uninstall"); start.ArgumentList.Add(version);
                    Process.Start(start);
                    return;
                }
            }
            catch (Exception) { MessageBox.Show("제거 준비에 실패했습니다. 앱을 닫고 다시 실행하세요.", "OpsPilot-X"); return; }
        }
        app.Run(new SetupWindow(version));
    }

    private sealed class SetupWindow : Window
    {
        private readonly TextBlock status = new() { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 16, 0, 16) };
        private readonly Button action = new() { MinWidth = 120, Padding = new Thickness(20, 10, 20, 10), HorizontalAlignment = HorizontalAlignment.Right };
        private bool busy;
        public SetupWindow(string? uninstallVersion)
        {
            Title = uninstallVersion == null ? "OpsPilot-X 설치" : "OpsPilot-X 제거";
            Width = 650; Height = 430; ResizeMode = ResizeMode.NoResize; WindowStartupLocation = WindowStartupLocation.CenterScreen;
            FontFamily = new FontFamily("Segoe UI"); FontSize = 14; Background = Brushes.White;
            var panel = new StackPanel { Margin = new Thickness(34) };
            panel.Children.Add(new TextBlock { Text = "OpsPilot-X", FontSize = 27, FontWeight = FontWeights.SemiBold, Foreground = new SolidColorBrush(Color.FromRgb(17, 43, 58)) });
            panel.Children.Add(new TextBlock { Text = uninstallVersion == null ? "이 사용자에게 앱 설치" : "앱 제거", FontSize = 19, Margin = new Thickness(0, 20, 0, 12) });
            panel.Children.Add(new TextBlock { Text = uninstallVersion == null
                ? "근거 조사·시점 검증·사람 승인 워크스페이스입니다.\n합성 자료와 mock 작업을 사용하는 서명되지 않은 미리보기입니다."
                : "앱을 먼저 종료하세요. 업무 데이터와 계정은 보존합니다.", TextWrapping = TextWrapping.Wrap });
            status.Text = uninstallVersion == null ? "설치 위치: " + InstallRoot + "\nWebView2 Runtime이 설치되어 있어야 합니다. 관리자 권한은 필요하지 않습니다." : "제거할 버전: " + uninstallVersion;
            panel.Children.Add(status);
            action.Content = uninstallVersion == null ? "설치" : "앱 제거";
            action.Background = new SolidColorBrush(Color.FromRgb(8, 126, 128)); action.Foreground = Brushes.White;
            action.Click += async (_, _) =>
            {
                if (busy) return;
                busy = true; action.IsEnabled = false; status.Text = uninstallVersion == null ? "배포 파일을 검증하고 설치하고 있습니다…" : "앱 파일을 제거하고 있습니다…";
                try
                {
                    if (uninstallVersion == null)
                    {
                        var installed = await Task.Run(() =>
                        {
                            using var payload = Assembly.GetExecutingAssembly().GetManifestResourceStream("OpsPilot.Payload.zip") ?? throw new InvalidDataException("설치 데이터가 없습니다.");
                            return SetupEngine.Install(payload, InstallRoot, CompleteInstall);
                        });
                        status.Text = "설치가 완료됐습니다. 시작 메뉴에서 OpsPilot-X를 실행하세요.\n업무 데이터는 설치 폴더와 별도로 보존됩니다.";
                    }
                    else
                    {
                        EnsureAppClosed(uninstallVersion);
                        await Task.Run(() => SetupEngine.Uninstall(InstallRoot, uninstallVersion));
                        var shortcut = ShortcutPath(uninstallVersion);
                        if (File.Exists(shortcut)) File.Delete(shortcut);
                        Registry.CurrentUser.DeleteSubKeyTree(RegistryPath(uninstallVersion), false);
                        status.Text = "앱을 제거했습니다. 업무 데이터와 계정은 보존했습니다.";
                    }
                    action.Content = "닫기"; action.IsEnabled = true; action.Click += (_, _) => Close();
                }
                catch (Exception error)
                {
                    status.Text = error is InvalidDataException ? error.Message : "완료하지 못했습니다. 앱을 닫고 설치 위치의 접근 권한·남은 공간을 확인하세요. 기존 업무 데이터는 변경하지 않습니다.";
                    busy = false; action.IsEnabled = true;
                }
            };
            panel.Children.Add(action); Content = panel;
            Closing += (_, e) => { if (busy && action.Content?.ToString() != "닫기") e.Cancel = true; };
        }
    }

    private static string ShortcutPath(string version) => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "OpsPilot-X " + version + ".lnk");
    private static void CompleteInstall(string installed)
    {
        var version = Path.GetFileName(installed);
        using (var existing = Registry.CurrentUser.OpenSubKey(RegistryPath(version)))
            if (existing != null) throw new InvalidDataException("This version is already registered");
        var shortcutCreated = false;
        var registryCreated = false;
        try
        {
            File.Copy(Environment.ProcessPath!, Path.Combine(installed, "Uninstall.exe"), false);
            CreateShortcut(installed, version);
            shortcutCreated = true;
            using var key = Registry.CurrentUser.CreateSubKey(RegistryPath(version));
            registryCreated = true;
            key.SetValue("DisplayName", "OpsPilot-X " + version);
            key.SetValue("DisplayVersion", version); key.SetValue("InstallLocation", installed);
            key.SetValue("UninstallString", $"\"{Path.Combine(installed, "Uninstall.exe")}\" --uninstall {version}");
            key.SetValue("NoModify", 1); key.SetValue("NoRepair", 1);
        }
        catch
        {
            if (registryCreated) Registry.CurrentUser.DeleteSubKeyTree(RegistryPath(version), false);
            if (shortcutCreated && File.Exists(ShortcutPath(version))) File.Delete(ShortcutPath(version));
            throw;
        }
    }
    private static void CreateShortcut(string installed, string version)
    {
        SetupEngine.NoLinks(Path.GetDirectoryName(ShortcutPath(version))!);
        if (File.Exists(ShortcutPath(version))) throw new IOException("Shortcut already exists");
        var shellType = Type.GetTypeFromProgID("WScript.Shell") ?? throw new IOException("Windows shortcuts unavailable");
        dynamic shell = Activator.CreateInstance(shellType)!;
        dynamic? shortcut = null;
        try
        {
            shortcut = shell.CreateShortcut(ShortcutPath(version));
            shortcut.TargetPath = Path.Combine(installed, "OpsPilot-X.exe");
            shortcut.WorkingDirectory = installed; shortcut.Description = "OpsPilot-X 근거 검증 워크스페이스"; shortcut.Save();
        }
        catch { if (File.Exists(ShortcutPath(version))) File.Delete(ShortcutPath(version)); throw; }
        finally
        {
            if (shortcut != null) System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shortcut);
            System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shell);
        }
    }

    private static void EnsureAppClosed(string version)
    {
        var installed = SetupEngine.VersionPath(InstallRoot, version) + Path.DirectorySeparatorChar;
        foreach (var process in Process.GetProcessesByName("OpsPilot-X"))
        {
            using (process)
                if (process.MainModule?.FileName?.StartsWith(installed, StringComparison.OrdinalIgnoreCase) == true)
                    throw new InvalidDataException("OpsPilot-X를 종료한 후 다시 제거하세요.");
        }
    }
}
