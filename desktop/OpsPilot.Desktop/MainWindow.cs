using System.ComponentModel;
using System.Windows;
using System.Windows.Controls;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;
namespace OpsPilot.Desktop;

public sealed class MainWindow : Window
{
    private readonly string data;
    private readonly Grid layout = new();
    private readonly TextBlock status = new() { TextWrapping = TextWrapping.Wrap, FontSize = 18, Margin = new Thickness(0,20,0,24) };
    private readonly StackPanel message = new() { Margin = new Thickness(48), VerticalAlignment = VerticalAlignment.Center, MaxWidth = 650 };
    private readonly Button retry = new() { Content = "다시 시도", Padding = new Thickness(20,9,20,9), Margin = new Thickness(0,0,12,0) };
    private BackendProcess? backend;
    private WebView2? web;
    private CancellationTokenSource? startup;
    private bool closing, closed;

    public MainWindow(string dataDirectory)
    {
        data = dataDirectory; Title = "OpsPilot-X · 로컬 Preview"; Width = 1200; Height = 820; MinWidth = 960; MinHeight = 640;
        WindowStartupLocation = WindowStartupLocation.CenterScreen; FontFamily = new System.Windows.Media.FontFamily("Segoe UI"); FontSize = 14;
        Background = System.Windows.Media.Brushes.WhiteSmoke; Content = layout;
        message.Children.Add(new TextBlock { Text = "OpsPilot-X", FontSize = 32, FontWeight = FontWeights.SemiBold }); message.Children.Add(status);
        var buttons = new StackPanel { Orientation = Orientation.Horizontal }; message.Children.Add(buttons); buttons.Children.Add(retry);
        var close = new Button { Content = "종료", Padding = new Thickness(20,9,20,9) }; buttons.Children.Add(close); close.Click += (_, _) => Close();
        layout.Children.Add(message); retry.Click += async (_, _) => await StartAsync();
        Loaded += async (_, _) => await StartAsync(); Closing += OnClosing;
    }

    private async Task StartAsync()
    {
        retry.IsEnabled = false; status.Text = "구성 확인 · 로컬 서비스를 시작하고 있습니다…";
        startup?.Dispose(); startup = new CancellationTokenSource(); var cancellation = startup.Token;
        var process = new BackendProcess(); backend = process;
        process.Exited += () => Dispatcher.BeginInvoke(async () => { if (!closing && ReferenceEquals(backend, process)) await FailAsync("로컬 서비스가 종료되었습니다. 다시 시도하려면 버튼을 누르세요."); });
        try
        {
            // Probe before requesting credentials so a missing runtime has a clear recovery path.
            _ = CoreWebView2Environment.GetAvailableBrowserVersionString();
            var origin = await process.StartAsync(data, () =>
            {
                if (closing || cancellation.IsCancellationRequested) return Task.FromResult<object?>(null);
                status.Text = "최초 설정이 필요합니다. 두 역할의 계정을 직접 지정하세요.";
                var setup = new SetupWindow(this); setup.ShowDialog();
                status.Text = "계정 설정을 확인하고 로컬 서비스를 준비하고 있습니다…";
                return Task.FromResult(setup.Accounts);
            }, cancellation);
            cancellation.ThrowIfCancellationRequested();
            status.Text = "로그인 화면을 준비하고 있습니다…";
            web = new WebView2 { Visibility = Visibility.Hidden };
            layout.Children.Add(web);
            var options = new CoreWebView2EnvironmentOptions { AreBrowserExtensionsEnabled = false, ExclusiveUserDataFolderAccess = true };
            var environment = await CoreWebView2Environment.CreateAsync(null, Path.Combine(data, "WebView2"), options);
            cancellation.ThrowIfCancellationRequested();
            await web.EnsureCoreWebView2Async(environment);
            cancellation.ThrowIfCancellationRequested();
            var core = web.CoreWebView2;
            var settings = core.Settings;
            settings.AreHostObjectsAllowed = false; settings.IsWebMessageEnabled = false; settings.AreDevToolsEnabled = false;
            settings.AreDefaultContextMenusEnabled = false; settings.AreBrowserAcceleratorKeysEnabled = false;
            settings.IsGeneralAutofillEnabled = false; settings.IsPasswordAutosaveEnabled = false; settings.IsStatusBarEnabled = false;
            settings.IsBuiltInErrorPageEnabled = false;
            core.CookieManager.DeleteAllCookies();
            core.NavigationStarting += (_, e) => e.Cancel = !DesktopPolicy.IsOwnOrigin(origin, e.Uri);
            core.FrameNavigationStarting += (_, e) => e.Cancel = true;
            core.NewWindowRequested += (_, e) => e.Handled = true;
            core.DownloadStarting += (_, e) => { e.Cancel = true; e.Handled = true; };
            core.PermissionRequested += (_, e) => { e.State = CoreWebView2PermissionState.Deny; e.Handled = true; };
            core.LaunchingExternalUriScheme += (_, e) => e.Cancel = true;
            core.ServerCertificateErrorDetected += (_, e) => e.Action = CoreWebView2ServerCertificateErrorAction.Cancel;
            core.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All, CoreWebView2WebResourceRequestSourceKinds.All);
            core.WebResourceRequested += (_, e) =>
            {
                if (!DesktopPolicy.IsOwnOrigin(origin, e.Request.Uri)) { e.Response = environment.CreateWebResourceResponse(null, 403, "Blocked", "Content-Type: text/plain"); return; }
                e.Request.Headers.SetHeader(DesktopPolicy.TokenHeader, process.Token);
            };
            core.ProcessFailed += async (_, _) => { if (!closing && ReferenceEquals(backend, process)) await FailAsync("앱 화면 프로세스가 종료되었습니다. 다시 시도하세요."); };
            core.NavigationCompleted += async (_, e) =>
            {
                if (closing || !ReferenceEquals(backend, process)) return;
                if (!e.IsSuccess) { await FailAsync("로그인 화면을 불러오지 못했습니다. 다시 시도하세요."); return; }
                message.Visibility = Visibility.Collapsed; if (web != null) web.Visibility = Visibility.Visible;
            };
            core.Navigate(origin.AbsoluteUri);
        }
        catch (OperationCanceledException) { if (!closing && ReferenceEquals(backend, process)) await FailAsync("계정 설정이 취소되었습니다. 계정을 만들지 않았습니다."); }
        catch (WebView2RuntimeNotFoundException) { await FailAsync("Microsoft Edge WebView2 Evergreen Runtime이 필요합니다. Runtime을 설치한 후 다시 실행하세요."); }
        catch (Exception e) { if (!closing && ReferenceEquals(backend, process)) await FailAsync(DesktopPolicy.SafeFailure(e)); }
    }

    private async Task FailAsync(string text)
    {
        if (closing) return;
        startup?.Cancel();
        status.Text = text; message.Visibility = Visibility.Visible; retry.IsEnabled = false;
        web?.Dispose(); if (web != null) layout.Children.Remove(web); web = null;
        var process = backend; backend = null;
        if (process != null) await process.DisposeAsync();
        if (!closing) retry.IsEnabled = true;
    }

    private async void OnClosing(object? sender, CancelEventArgs e)
    {
        if (closed) return;
        e.Cancel = true; if (closing) return; closing = true; startup?.Cancel(); retry.IsEnabled = false;
        web?.Dispose(); web = null;
        var process = backend; backend = null;
        if (process != null) await process.DisposeAsync();
        closed = true; Close();
    }
}
