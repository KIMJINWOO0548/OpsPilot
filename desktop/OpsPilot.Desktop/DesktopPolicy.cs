using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace OpsPilot.Desktop;

public sealed class DesktopBackendException(int? winError) : Exception("Desktop backend failed")
{
    public int? WinError { get; } = winError;
}

public sealed record DesktopStartupFailure(string Reason, string NextAction);

public static class DesktopPolicy
{
    public const string TokenHeader = "X-OpsPilot-Desktop-Token";
    public const string DefaultWindowTitle = "OpsPilot-X · 로컬 운영 검증";
    public static string DataDirectory(string[] args)
    {
        if (args.Length == 0) return Path.GetFullPath(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "OpsPilot-X"));
        if (args.Length != 2 || args[0] != "--data-dir" || !Path.IsPathFullyQualified(args[1])) throw new ArgumentException("Absolute data directory required");
        return Path.TrimEndingDirectorySeparator(Path.GetFullPath(args[1]));
    }
    public static string InstanceName(string path) => @"Local\OpsPilot-X-" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Path.TrimEndingDirectorySeparator(Path.GetFullPath(path)).ToUpperInvariant())));
    public static Uri ReadyOrigin(string json, string token)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            if (root.GetProperty("event").GetString() != "ready" || root.GetProperty("token").GetString() != token || token.Length != 64 || token.Any(c => !"0123456789abcdef".Contains(c))) throw new ArgumentException("Invalid readiness");
            var value = root.GetProperty("origin").GetString()!;
            if (!Uri.TryCreate(value, UriKind.Absolute, out var uri) || uri.Scheme != "http" || uri.Host != "127.0.0.1" || uri.Port < 1 || uri.UserInfo.Length != 0 || uri.AbsolutePath != "/" || uri.Query.Length != 0 || uri.Fragment.Length != 0 || (value != $"http://127.0.0.1:{uri.Port}" && value != $"http://127.0.0.1:{uri.Port}/")) throw new ArgumentException("Invalid readiness origin");
            return uri;
        }
        catch (Exception e) when (e is JsonException or KeyNotFoundException or InvalidOperationException) { throw new ArgumentException("Invalid readiness", e); }
    }
    public static bool IsOwnOrigin(Uri origin, string value)
    {
        var authority = $"http://127.0.0.1:{origin.Port}";
        return Uri.TryCreate(value, UriKind.Absolute, out var uri) && uri.Scheme == "http" && uri.Host == "127.0.0.1" && uri.Port == origin.Port && uri.UserInfo.Length == 0 && (value == authority || value.StartsWith(authority + "/", StringComparison.Ordinal) || value.StartsWith(authority + "?", StringComparison.Ordinal) || value.StartsWith(authority + "#", StringComparison.Ordinal));
    }
    public static string WorkspaceTitle(Uri origin, string source, string documentTitle)
    {
        if (!IsOwnOrigin(origin, source) || !Uri.TryCreate(source, UriKind.Absolute, out var page) ||
            page.AbsolutePath != "/" || page.Query.Length != 0) return DefaultWindowTitle;
        return documentTitle switch
        {
            "OpsPilot-X · 로컬 연결 준비" or "OpsPilot-X · 로그인" or "OpsPilot-X · 근거 조사" or "OpsPilot-X · 근거 타임라인" or
            "OpsPilot-X · 승인함" or "OpsPilot-X · 초안 근거 비교" => documentTitle,
            _ => DefaultWindowTitle,
        };
    }
    // Child output and exception messages may contain credentials.
    public static DesktopStartupFailure SafeFailure(Exception e) => e switch
    {
        DesktopBackendException { WinError: 10014 } => new("Windows 소켓 오류(10014)로 로컬 서비스를 시작하지 못했습니다.", "앱을 종료한 뒤 네트워크 환경을 확인하고 다시 실행하세요."),
        TimeoutException => new("로컬 서비스 응답 시간이 초과되었습니다.", "잠시 기다린 뒤 다시 시도하세요."),
        FileNotFoundException => new("앱 구성 파일이 없습니다.", "설치 파일로 앱을 다시 설치하거나 전체 배포 파일을 풀고 다시 실행하세요."),
        _ => new("앱을 시작하지 못했습니다.", "다시 시도하세요. 같은 문제가 계속되면 설치 파일을 확인하세요."),
    };
}
