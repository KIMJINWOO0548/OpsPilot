using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace OpsPilot.Setup;

public sealed record ReleaseManifest(string Product, string Version, Dictionary<string, string> Files);

public static class SetupEngine
{
    public static readonly JsonSerializerOptions JsonOptions = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };

    public static string VersionPath(string root, string version)
    {
        if (!Regex.IsMatch(version, @"^\d+\.\d+\.\d+(?:-[a-z0-9]+(?:\.[a-z0-9]+)*)?$"))
            throw new InvalidDataException("Invalid release version");
        return Path.Combine(Path.GetFullPath(root), version);
    }

    private static string EntryPath(string root, string name)
    {
        if (string.IsNullOrWhiteSpace(name) || name.Contains('\\') || name.Contains(':') ||
            name.StartsWith('/') || name.Split('/').Any(p => p is "" or "." or ".." || p.EndsWith('.') || p.EndsWith(' ')))
            throw new InvalidDataException("Unsafe package path");
        var result = Path.GetFullPath(Path.Combine(root, name.Replace('/', Path.DirectorySeparatorChar)));
        if (!result.StartsWith(Path.GetFullPath(root) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Package path escaped installation");
        return result;
    }

    public static void NoLinks(string path)
    {
        for (var current = new DirectoryInfo(Path.GetFullPath(path)); current != null; current = current.Parent)
            if (current.Exists && (current.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("Linked installation directories are not supported");
    }

    private static void CheckTree(string directory)
    {
        foreach (var path in Directory.EnumerateFileSystemEntries(directory))
        {
            var attributes = File.GetAttributes(path);
            if ((attributes & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("Linked installation entries are not supported");
            if ((attributes & FileAttributes.Directory) != 0) CheckTree(path);
        }
    }

    public static string Install(Stream payload, string root, Action<string>? finalize = null)
    {
        root = Path.GetFullPath(root);
        NoLinks(root);
        using var archive = new ZipArchive(payload, ZipArchiveMode.Read, true);
        var manifestEntry = archive.GetEntry("release-manifest.json") ?? throw new InvalidDataException("Release manifest missing");
        if (manifestEntry.Length > 8 * 1024 * 1024) throw new InvalidDataException("Release manifest too large");
        ReleaseManifest manifest;
        using (var stream = manifestEntry.Open())
            manifest = JsonSerializer.Deserialize<ReleaseManifest>(stream, JsonOptions) ?? throw new InvalidDataException("Invalid manifest");
        if (manifest.Product != "OpsPilot-X" || manifest.Files == null || !manifest.Files.ContainsKey("OpsPilot-X.exe"))
            throw new InvalidDataException("Unexpected release product");
        var target = VersionPath(root, manifest.Version);
        if (Directory.Exists(target) || File.Exists(target)) throw new InvalidDataException("This version is already installed");
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        long total = 0;
        foreach (var entry in archive.Entries)
        {
            EntryPath(root, entry.FullName);
            if (!names.Add(entry.FullName) || ((entry.ExternalAttributes >> 16) & 0xF000) == 0xA000)
                throw new InvalidDataException("Duplicate or linked package entry");
            total = checked(total + entry.Length);
            if (total > 1024L * 1024 * 1024) throw new InvalidDataException("Package is too large");
            if (entry.FullName != "release-manifest.json" && !manifest.Files.ContainsKey(entry.FullName))
                throw new InvalidDataException("Unlisted package entry");
        }
        if (names.Count != manifest.Files.Count + 1 || manifest.Files.Keys.Any(name => !names.Contains(name)))
            throw new InvalidDataException("Incomplete package");
        foreach (var pair in manifest.Files)
            if (!Regex.IsMatch(pair.Value, "^[a-f0-9]{64}$")) throw new InvalidDataException("Invalid package digest");
        Directory.CreateDirectory(root);
        var staging = Path.Combine(root, "." + manifest.Version + "." + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(staging);
        var moved = false;
        try
        {
            foreach (var entry in archive.Entries)
            {
                var destination = EntryPath(staging, entry.FullName);
                Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                using (var input = entry.Open())
                using (var output = new FileStream(destination, FileMode.CreateNew, FileAccess.Write)) input.CopyTo(output);
                if (entry.FullName != "release-manifest.json")
                {
                    using var output = File.OpenRead(destination);
                    if (Convert.ToHexStringLower(SHA256.HashData(output)) != manifest.Files[entry.FullName])
                        throw new InvalidDataException("Package integrity check failed");
                }
            }
            NoLinks(root);
            CheckTree(staging);
            Directory.Move(staging, target);
            moved = true;
            finalize?.Invoke(target);
            return target;
        }
        catch
        {
            if (Directory.Exists(staging)) { NoLinks(staging); CheckTree(staging); Directory.Delete(staging, true); }
            if (moved && Directory.Exists(target)) { NoLinks(target); CheckTree(target); Directory.Delete(target, true); }
            throw;
        }
    }

    public static void Uninstall(string root, string version)
    {
        var target = VersionPath(root, version);
        NoLinks(target);
        if (!Directory.Exists(target)) throw new InvalidDataException("Installation not found");
        CheckTree(target);
        var manifest = JsonSerializer.Deserialize<ReleaseManifest>(File.ReadAllText(Path.Combine(target, "release-manifest.json")), JsonOptions);
        if (manifest == null || manifest.Product != "OpsPilot-X" || manifest.Version != version)
            throw new InvalidDataException("Installation ownership could not be verified");
        var allowed = new HashSet<string>(manifest.Files.Keys, StringComparer.OrdinalIgnoreCase) { "release-manifest.json", "Uninstall.exe" };
        foreach (var file in Directory.EnumerateFiles(target, "*", SearchOption.AllDirectories))
            if (!allowed.Contains(Path.GetRelativePath(target, file).Replace('\\', '/')))
                throw new InvalidDataException("Unexpected files found; installation was preserved");
        Directory.Delete(target, true);
    }
}
