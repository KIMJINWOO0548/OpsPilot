using System.Diagnostics;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text.Json;
namespace OpsPilot.Desktop;

internal sealed class BackendProcess : IAsyncDisposable
{
    private Process? child;
    private ChildJob? job;
    private bool stopping;
    private bool ready;
    public string Token { get; } = Convert.ToHexString(RandomNumberGenerator.GetBytes(32)).ToLowerInvariant();
    public event Action? Exited;
    public async Task<Uri> StartAsync(string data, Func<Task<object?>> setup, CancellationToken cancellation)
    {
        var bundle = AppContext.BaseDirectory;
        var python = Path.Combine(bundle, "backend", "python", "python.exe");
        var web = Path.Combine(bundle, "backend", "web", "dist");
        if (!File.Exists(python) || !File.Exists(Path.Combine(web, "index.html"))) throw new FileNotFoundException();
        job = new ChildJob();
        var start = new ProcessStartInfo(python) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true, StandardInputEncoding = System.Text.Encoding.UTF8, StandardOutputEncoding = System.Text.Encoding.UTF8, StandardErrorEncoding = System.Text.Encoding.UTF8, WorkingDirectory = bundle };
        foreach (var key in start.Environment.Keys.Where(k => k.StartsWith("PYTHON", StringComparison.OrdinalIgnoreCase) || k.StartsWith("OPSPILOT", StringComparison.OrdinalIgnoreCase)).ToArray()) start.Environment.Remove(key);
        foreach (var arg in new[] { "-I", "-B", "-u", "-m", "opspilot_x.desktop_runtime", "--data-dir", data, "--web-dir", web }) start.ArgumentList.Add(arg);
        child = new Process { StartInfo = start, EnableRaisingEvents = true };
        child.Exited += (_, _) => { if (!stopping && ready) Exited?.Invoke(); };
        if (!child.Start()) throw new InvalidOperationException();
        try { job.Add(child); } catch { child.Kill(true); throw; }
        var diagnostic = DrainErrorsAsync(child.StandardError);
        await child.StandardInput.WriteLineAsync(JsonSerializer.Serialize(new { token = Token }));
        await child.StandardInput.FlushAsync();
        while (true)
        {
            // Only machine startup reads have a deadline; setup waits for the human.
            var line = await child.StandardOutput.ReadLineAsync(cancellation).AsTask().WaitAsync(TimeSpan.FromSeconds(30), cancellation);
            if (line == null) throw new DesktopBackendException(await diagnostic);
            if (line.Length > 8192) throw new InvalidOperationException();
            using var doc = JsonDocument.Parse(line);
            var kind = doc.RootElement.GetProperty("event").GetString();
            if (kind == "setup_required" || kind == "setup_error")
            {
                var accounts = await setup();
                if (accounts == null) throw new OperationCanceledException();
                await child.StandardInput.WriteLineAsync(JsonSerializer.Serialize(accounts));
                await child.StandardInput.FlushAsync();
                continue;
            }
            var origin = DesktopPolicy.ReadyOrigin(line, Token);
            using var client = new HttpClient(new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false }) { Timeout = TimeSpan.FromSeconds(10) };
            client.DefaultRequestHeaders.Add(DesktopPolicy.TokenHeader, Token);
            using var response = await client.GetAsync(new Uri(origin, "/health"), cancellation);
            response.EnsureSuccessStatusCode();
            using var health = JsonDocument.Parse(await response.Content.ReadAsStringAsync(cancellation));
            if (!health.RootElement.GetProperty("ok").GetBoolean() || child.HasExited) throw new InvalidOperationException();
            ready = true;
            return origin;
        }
    }
    private static async Task<int?> DrainErrorsAsync(StreamReader reader)
    {
        var diagnostic = new System.Text.StringBuilder();
        try
        {
            var buffer = new char[1024]; int count;
            while ((count = await reader.ReadAsync(buffer)) > 0)
                if (diagnostic.Length < 512) diagnostic.Append(buffer, 0, Math.Min(count, 512 - diagnostic.Length));
        }
        catch (IOException) { }
        return diagnostic.ToString().Contains("(WinError 10014).", StringComparison.Ordinal) ? 10014 : null;
    }
    public async ValueTask DisposeAsync()
    {
        stopping = true;
        if (child != null)
        {
            try
            {
                if (!child.HasExited)
                {
                    await child.StandardInput.WriteLineAsync("{\"event\":\"stop\"}"); await child.StandardInput.FlushAsync(); child.StandardInput.Close();
                    try { await child.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(5)); } catch (TimeoutException) { if (!child.HasExited) child.Kill(true); }
                }
            }
            catch (Exception e) when (e is IOException or InvalidOperationException or System.ComponentModel.Win32Exception) { job?.Dispose(); }
            finally { job?.Dispose(); child.Dispose(); child = null; }
        }
        job?.Dispose(); job = null;
    }
}
