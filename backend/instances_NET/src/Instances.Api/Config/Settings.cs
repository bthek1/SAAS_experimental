using System.Net;
using System.Text.RegularExpressions;

namespace Instances.Api.Config;

/// <summary>
/// Everything the service reads from its environment, with the same names and profiles as
/// Django's `instances` (`core/settings/`), so `.env` and the deploys need no change.
///
/// `SETTINGS` picks the profile: dev (default), test, e2e, prod or loadtest. The test
/// profiles never read `.env` and always trust the published dev key pair (#33); prod and
/// loadtest require real keys and tokens, and loadtest refuses public hosts.
/// </summary>
public sealed record Settings
{
    public const string ServiceName = "instances";

    public required string Profile { get; init; }
    public required bool Debug { get; init; }
    public required string DatabaseUrl { get; init; }
    public required string JwtVerifyingKey { get; init; }
    public required string InboundPeerToken { get; init; }
    public required string OutboundPeerToken { get; init; }
    public required string CatalogInternalUrl { get; init; }
    public required TimeSpan PeerConnectTimeout { get; init; }
    public required TimeSpan PeerReadTimeout { get; init; }
    public required bool CacheEnabled { get; init; }
    public required string CacheRedisUrl { get; init; }
    public required IReadOnlyList<string> AllowedHosts { get; init; }
    public required IReadOnlyList<string> CorsAllowedOrigins { get; init; }
    public required IReadOnlyList<Regex> CorsAllowedOriginPatterns { get; init; }
    public required IReadOnlyList<IPNetwork> MetricsAllowedNetworks { get; init; }
    public required bool HttpsRedirect { get; init; }
    public required bool LoadTest { get; init; }
    public int DatabasePoolSize { get; init; } = 15;

    static readonly string[] Profiles = ["dev", "test", "e2e", "prod", "loadtest"];

    public bool IsTestProfile => Profile is "test" or "e2e";

    /// <summary>Read the settings from the process environment and, on dev, the root `.env`.</summary>
    public static Settings Load() => Load(
        Environment.GetEnvironmentVariables()
            .Cast<System.Collections.DictionaryEntry>()
            .ToDictionary(e => (string)e.Key, e => (string?)e.Value ?? ""),
        DotEnv.FindAndRead());

    /// <param name="dotEnv">The root `.env`, which only dev, prod and loadtest read.</param>
    public static Settings Load(IReadOnlyDictionary<string, string> environment, IReadOnlyDictionary<string, string>? dotEnv = null)
    {
        var profile = environment.GetValueOrDefault("SETTINGS", "dev");
        if (!Profiles.Contains(profile))
        {
            throw new SettingsException(
                $"Unknown SETTINGS value: '{profile}'. Must be one of {string.Join(", ", Profiles)}.");
        }

        var env = new Env(environment, profile is "dev" or "prod" or "loadtest" ? dotEnv : null);
        return profile switch
        {
            "dev" => Dev(env),
            "test" => Test(env, profile),
            "e2e" => Test(env, profile),
            "prod" => Prod(env, profile),
            _ => LoadTestProfile(env),
        };
    }

    static Settings Dev(Env env) => Common(env, "dev") with
    {
        Debug = true,
        DatabaseUrl = env.Str("INSTANCES_DATABASE_URL",
            "postgres://appuser:apppassword@localhost:5437/instancesdb"),
        JwtVerifyingKey = env.Multiline("JWT_VERIFYING_KEY") is { Length: > 0 } key ? key : DevKeys.VerifyingKey,
        InboundPeerToken = env.Str("CATALOG_TO_INSTANCES_TOKEN", "") is { Length: > 0 } inbound
            ? inbound : "dev-catalog-to-instances",
        OutboundPeerToken = env.Str("INSTANCES_TO_CATALOG_TOKEN", "") is { Length: > 0 } outbound
            ? outbound : "dev-instances-to-catalog",
        AllowedHosts = env.List("ALLOWED_HOSTS", ["localhost", "127.0.0.1"]),
        CorsAllowedOrigins = env.List("CORS_ALLOWED_ORIGINS", ["http://localhost:5174"]),
        CorsAllowedOriginPatterns = [new Regex(@"^http://192\.168\.\d+\.\d+:\d+$")],
    };

    static Settings Test(Env env, string profile) => Common(env, profile) with
    {
        Debug = false,
        // Postgres only (#42), so even tests name a database: a throwaway one.
        DatabaseUrl = env.Required("INSTANCES_DATABASE_URL"),
        // Tests sign with the published pair, whatever a developer's environment says (#33).
        JwtVerifyingKey = DevKeys.VerifyingKey,
        InboundPeerToken = "test-catalog-to-instances",
        OutboundPeerToken = "test-instances-to-catalog",
        CatalogInternalUrl = env.Str("CATALOG_INTERNAL_URL",
            profile == "e2e" ? "http://localhost:8016" : "http://localhost:8006"),
        // Off, so tests see fresh data. Cache tests turn it on themselves.
        CacheEnabled = false,
        AllowedHosts = ["localhost", "127.0.0.1"],
        CorsAllowedOrigins = env.List("CORS_ALLOWED_ORIGINS",
            profile == "e2e" ? ["http://localhost:5184"] : []),
        CorsAllowedOriginPatterns = [],
    };

    static Settings Prod(Env env, string profile)
    {
        var key = env.Multiline("JWT_VERIFYING_KEY");
        if (key.Length == 0)
        {
            throw new SettingsException("Set JWT_VERIFYING_KEY.");
        }
        if (key.Trim() == DevKeys.VerifyingKey.Trim())
        {
            throw new SettingsException("JWT_VERIFYING_KEY is the published dev key.");
        }
        var inbound = env.Str("CATALOG_TO_INSTANCES_TOKEN", "");
        var outbound = env.Str("INSTANCES_TO_CATALOG_TOKEN", "");
        if (inbound.Length == 0 || outbound.Length == 0)
        {
            throw new SettingsException("Set CATALOG_TO_INSTANCES_TOKEN and INSTANCES_TO_CATALOG_TOKEN.");
        }
        return Common(env, profile) with
        {
            Debug = false,
            DatabaseUrl = env.Required("INSTANCES_DATABASE_URL"),
            JwtVerifyingKey = key,
            InboundPeerToken = inbound,
            OutboundPeerToken = outbound,
            // No default: the cache fails open, so a wrong URL would otherwise run uncached
            // with no other symptom.
            CacheRedisUrl = env.Required("CACHE_REDIS_URL"),
            AllowedHosts = env.RequiredList("ALLOWED_HOSTS"),
            CorsAllowedOrigins = env.List("CORS_ALLOWED_ORIGINS", []),
            CorsAllowedOriginPatterns = [],
            HttpsRedirect = true,
        };
    }

    /// <summary>prod over plain HTTP for k6 on a private network (#9).</summary>
    static Settings LoadTestProfile(Env env)
    {
        var settings = Prod(env, "loadtest") with { HttpsRedirect = false, LoadTest = true };
        var publicHosts = settings.AllowedHosts.Where(host => !IsPrivateHost(host)).ToList();
        if (publicHosts.Count > 0)
        {
            throw new SettingsException(
                $"SETTINGS=loadtest refuses ALLOWED_HOSTS [{string.Join(", ", publicHosts)}]: the HTTPS "
                + "redirect is off here, so it only runs behind private addresses");
        }
        return settings;
    }

    static Settings Common(Env env, string profile) => new()
    {
        Profile = profile,
        Debug = false,
        DatabaseUrl = "",
        JwtVerifyingKey = "",
        InboundPeerToken = "",
        OutboundPeerToken = "",
        CatalogInternalUrl = env.Str("CATALOG_INTERNAL_URL", "http://localhost:8006"),
        PeerConnectTimeout = TimeSpan.FromSeconds(env.Float("PEER_CONNECT_TIMEOUT", 0.5)),
        PeerReadTimeout = TimeSpan.FromSeconds(env.Float("PEER_READ_TIMEOUT", 2.0)),
        CacheEnabled = env.Bool("CACHE_ENABLED", true),
        CacheRedisUrl = env.Str("CACHE_REDIS_URL", "redis://localhost:6380/1"),
        AllowedHosts = [],
        CorsAllowedOrigins = [],
        CorsAllowedOriginPatterns = [],
        MetricsAllowedNetworks = env.List("METRICS_ALLOWED_CIDRS", ["127.0.0.1/32", "::1/128"])
            .Select(IPNetwork.Parse).ToList(),
        HttpsRedirect = false,
        LoadTest = false,
        DatabasePoolSize = env.Int("DB_POOL_SIZE", 15),
    };

    static readonly string[] PrivateSuffixes = [".lan", ".internal", ".local", ".localhost"];

    public static bool IsPrivateHost(string host)
    {
        if (host == "localhost" || PrivateSuffixes.Any(host.EndsWith))
        {
            return true;
        }
        if (!IPAddress.TryParse(host.Trim('[', ']'), out var address))
        {
            return false;
        }
        if (IPAddress.IsLoopback(address))
        {
            return true;
        }
        if (address.IsIPv4MappedToIPv6)
        {
            address = address.MapToIPv4();
        }
        if (address.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork)
        {
            var b = address.GetAddressBytes();
            return b[0] == 10
                || (b[0] == 172 && b[1] >= 16 && b[1] <= 31)
                || (b[0] == 192 && b[1] == 168)
                || (b[0] == 169 && b[1] == 254)
                || (b[0] == 100 && b[1] >= 64 && b[1] <= 127)
                || b[0] == 0;
        }
        return address.IsIPv6LinkLocal || address.IsIPv6UniqueLocal || address.IsIPv6SiteLocal;
    }
}

public sealed class SettingsException(string message) : Exception(message);

/// <summary>The environment first, then `.env` (dev, prod and loadtest only), as the Django version read them.</summary>
sealed class Env(IReadOnlyDictionary<string, string> environment, IReadOnlyDictionary<string, string>? dotEnv)
{
    string? Raw(string name) =>
        environment.TryGetValue(name, out var value) ? value
        : dotEnv is not null && dotEnv.TryGetValue(name, out var fromFile) ? fromFile
        : null;

    public string Str(string name, string fallback) => Raw(name) ?? fallback;

    public string Required(string name) =>
        Raw(name) is { Length: > 0 } value ? value : throw new SettingsException($"Set {name}.");

    /// <summary>A PEM kept on one line with `\n` escapes, as `.env.example` explains.</summary>
    public string Multiline(string name) => (Raw(name) ?? "").Replace("\\n", "\n");

    public IReadOnlyList<string> List(string name, IReadOnlyList<string> fallback) =>
        Raw(name) is { } value
            ? value.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            : fallback;

    public IReadOnlyList<string> RequiredList(string name) =>
        List(name, []) is { Count: > 0 } values ? values : throw new SettingsException($"Set {name}.");

    public bool Bool(string name, bool fallback) => Raw(name)?.Trim().ToLowerInvariant() switch
    {
        null => fallback,
        "true" or "on" or "ok" or "y" or "yes" or "1" => true,
        _ => false,
    };

    public double Float(string name, double fallback) =>
        Raw(name) is { Length: > 0 } value
            ? double.Parse(value, System.Globalization.CultureInfo.InvariantCulture)
            : fallback;

    public int Int(string name, int fallback) =>
        Raw(name) is { Length: > 0 } value ? int.Parse(value, System.Globalization.CultureInfo.InvariantCulture) : fallback;
}

/// <summary>The repo root's `.env`: absent inside images, where env vars come from the deploy.</summary>
static class DotEnv
{
    public static IReadOnlyDictionary<string, string>? FindAndRead()
    {
        for (var dir = new DirectoryInfo(AppContext.BaseDirectory); dir is not null; dir = dir.Parent)
        {
            var candidate = Path.Combine(dir.FullName, ".env");
            if (File.Exists(candidate) && File.Exists(Path.Combine(dir.FullName, "AGENTS.md")))
            {
                return Parse(File.ReadAllLines(candidate));
            }
        }
        return null;
    }

    public static IReadOnlyDictionary<string, string> Parse(IEnumerable<string> lines)
    {
        var values = new Dictionary<string, string>();
        foreach (var raw in lines)
        {
            var line = raw.Trim();
            if (line.Length == 0 || line.StartsWith('#'))
            {
                continue;
            }
            if (line.StartsWith("export ", StringComparison.Ordinal))
            {
                line = line[7..].TrimStart();
            }
            var equals = line.IndexOf('=');
            if (equals <= 0)
            {
                continue;
            }
            var key = line[..equals].Trim();
            var value = line[(equals + 1)..].Trim();
            if (value.Length >= 2 && (value[0] is '"' or '\'') && value[^1] == value[0])
            {
                value = value[1..^1];
            }
            values[key] = value;
        }
        return values;
    }
}
