using OpsPilot.Desktop;
using System.Diagnostics;
if (args.Contains("--child")) { Console.ReadLine(); return; }
static void Check(bool condition, string name) { if (!condition) throw new Exception(name); }
static void Reject(Action action) { try { action(); } catch (ArgumentException) { return; } throw new Exception("Expected rejection"); }
var token = new string('a', 64);
var origin = DesktopPolicy.ReadyOrigin("{\"event\":\"ready\",\"origin\":\"http://127.0.0.1:12345\",\"token\":\"" + token + "\"}", token);
Check(DesktopPolicy.IsOwnOrigin(origin, "http://127.0.0.1:12345/api"), "own request");
foreach (var url in new[] { "https://127.0.0.1:12345", "http://localhost:12345", "http://127.0.0.1:12346", "file:///tmp/a", "javascript:alert(1)", "http://127.0.0.1:12345@evil.test" }) Check(!DesktopPolicy.IsOwnOrigin(origin, url), "external request");
foreach (var url in new[] { "http://localhost:12345", "http://127.0.0.1:0", "http://127.0.0.1:12345/path", "http://127.0.0.1:12345?x=y", "http://user@127.0.0.1:12345" }) Reject(() => DesktopPolicy.ReadyOrigin(System.Text.Json.JsonSerializer.Serialize(new { @event = "ready", origin = url, token }), token));
foreach (var url in new[] { "http://127.1:12345", "http://2130706433:12345", "http://127.0.0.1:012345" })
{
    Reject(() => DesktopPolicy.ReadyOrigin(System.Text.Json.JsonSerializer.Serialize(new { @event = "ready", origin = url, token }), token));
    Check(!DesktopPolicy.IsOwnOrigin(origin, url), "reject alternate origin spelling");
}
Reject(() => DesktopPolicy.ReadyOrigin("{}", token));
Reject(() => DesktopPolicy.ReadyOrigin(System.Text.Json.JsonSerializer.Serialize(new { @event = "ready", origin = origin.ToString(), token = new string('b',64) }), token));
Reject(() => DesktopPolicy.DataDirectory(new[] { "--data-dir", "relative" }));
Reject(() => DesktopPolicy.DataDirectory(new[] { "--server-url", "http://evil" }));
Check(DesktopPolicy.DataDirectory(new[] { "--data-dir", Path.GetTempPath() }) == Path.TrimEndingDirectorySeparator(Path.GetFullPath(Path.GetTempPath())), "absolute canonical path");
Check(DesktopPolicy.SafeFailure(new Exception(token)).Contains(token) == false, "secret-free diagnostic");
Check(DesktopPolicy.SafeFailure(new DesktopBackendException(10014)).Contains("10014"), "specific safe socket diagnostic");
Check(DesktopPolicy.InstanceName(Path.GetTempPath()) == DesktopPolicy.InstanceName(Path.Combine(Path.GetTempPath(), ".")), "single instance canonical path");
if (OperatingSystem.IsWindows())
{
    using var child = Process.Start(new ProcessStartInfo(Environment.ProcessPath!) { ArgumentList = { "--child" }, UseShellExecute = false, RedirectStandardInput = true, CreateNoWindow = true })!;
    using (var job = new ChildJob()) { job.Add(child); Check(!child.HasExited, "owned child alive"); }
    Check(child.WaitForExit(5000), "job closes owned child");
    using var graceful = Process.Start(new ProcessStartInfo(Environment.ProcessPath!) { ArgumentList = { "--child" }, UseShellExecute = false, RedirectStandardInput = true, CreateNoWindow = true })!;
    using var gracefulJob = new ChildJob(); gracefulJob.Add(graceful); graceful.StandardInput.Close();
    Check(graceful.WaitForExit(5000), "stdin EOF child exit");
}
Console.WriteLine("Desktop policy checks passed");
