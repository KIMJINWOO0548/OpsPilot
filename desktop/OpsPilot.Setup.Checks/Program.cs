using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;
using OpsPilot.Setup;

var checks = 0;
void Check(bool condition, string name) { if (!condition) throw new Exception(name); checks++; }
void Reject(Action action, string name)
{
    try { action(); } catch (InvalidDataException) { checks++; return; }
    throw new Exception(name);
}
MemoryStream Payload(string file = "OpsPilot-X.exe", bool tamper = false)
{
    var stream = new MemoryStream();
    var bytes = "test executable"u8.ToArray();
    using (var zip = new ZipArchive(stream, ZipArchiveMode.Create, true))
    {
        using (var entry = zip.CreateEntry(file).Open()) entry.Write(bytes);
        var manifest = new ReleaseManifest("OpsPilot-X", "0.3.0-preview.1",
            new() { [file] = tamper ? new string('0', 64) : Convert.ToHexStringLower(SHA256.HashData(bytes)) });
        using var output = zip.CreateEntry("release-manifest.json").Open();
        JsonSerializer.Serialize(output, manifest, SetupEngine.JsonOptions);
    }
    stream.Position = 0;
    return stream;
}
var root = Path.Combine(Path.GetTempPath(), "OpsPilot 설치 검증 " + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
try
{
    var installRoot = Path.Combine(root, "Programs");
    var dataRoot = Path.Combine(root, "Data");
    Directory.CreateDirectory(dataRoot);
    File.WriteAllText(Path.Combine(dataRoot, "work.sqlite3"), "must survive");
    using (var payload = Payload())
    {
        var installed = SetupEngine.Install(payload, installRoot);
        Check(File.Exists(Path.Combine(installed, "OpsPilot-X.exe")), "valid install");
        using var second = Payload();
        Reject(() => SetupEngine.Install(second, installRoot), "existing version overwrite");
        SetupEngine.Uninstall(installRoot, "0.3.0-preview.1");
        Check(!Directory.Exists(installed), "owned install removed");
    }
    Check(File.ReadAllText(Path.Combine(dataRoot, "work.sqlite3")) == "must survive", "data preserved");
    using (var traversal = Payload("../escape.exe"))
        Reject(() => SetupEngine.Install(traversal, installRoot), "zip traversal");
    Check(!File.Exists(Path.Combine(root, "escape.exe")), "no escaped file");
    using (var tampered = Payload(tamper: true))
        Reject(() => SetupEngine.Install(tampered, installRoot), "tampered payload");
    using (var finalizationFailure = Payload())
        Reject(() => SetupEngine.Install(finalizationFailure, installRoot, installed =>
        {
            File.WriteAllText(Path.Combine(installed, "Uninstall.exe"), "temporary owned file");
            throw new InvalidDataException("Simulated shortcut failure");
        }), "finalization rollback");
    Check(!Directory.Exists(Path.Combine(installRoot, "0.3.0-preview.1")), "failed finalization leaves no blocked version");
    using (var retry = Payload())
    {
        SetupEngine.Install(retry, installRoot);
        SetupEngine.Uninstall(installRoot, "0.3.0-preview.1");
        Check(true, "install after finalization failure");
    }
    Reject(() => SetupEngine.Uninstall(installRoot, "../Data"), "uninstall traversal");
    Console.WriteLine($"Setup checks: {checks} passed");
}
finally
{
    Directory.Delete(root, true);
}
