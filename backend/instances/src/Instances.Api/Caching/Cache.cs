using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Instances.Api.Config;
using Prometheus;
using StackExchange.Redis;

namespace Instances.Api.Caching;

/// <summary>Where cached bytes live. Redis in every deploy; tests can swap it.</summary>
public interface ICacheStore
{
    Task<byte[]?> Get(string key);
    Task Set(string key, byte[] value, TimeSpan? ttl);
    /// <summary>The value at `key`, storing `value` first if there is none.</summary>
    Task<string> GetOrAdd(string key, string value);
}

/// <summary>
/// Server-side cache for expensive reads, with `catalog/cache.py`'s rules (#11):
///
/// - an owner id is required, so a key cannot be built without a tenant;
/// - a Redis failure is logged and counted, then the value is computed: a cache problem
///   never fails a request;
/// - params come from validated data, never a raw query string;
/// - each owner has a random generation, part of every key; bumping it after a commit
///   makes their entries unreachable without scanning keys.
///
/// Values are the response's JSON bytes, never pickle, under a key prefix of their own, so
/// this never reads the Django version's entries.
/// </summary>
public sealed class Cache(ICacheStore store, Settings settings, ILogger<Cache> logger)
{
    public static readonly IReadOnlySet<string> Groups = new HashSet<string> { "dashboard", "dashboard-scores", "pdf" };
    const string GenerationGroup = "generation";

    static readonly Counter Requests = Metrics.CreateCounter(
        "app_cache_requests_total", "Cached reads by group and result (hit, miss, error).", "group", "result");

    bool _enabledOverride = true;

    /// <summary>For tests that turn the cache on or off at run time.</summary>
    public bool Enabled
    {
        get => settings.CacheEnabled && _enabledOverride;
        set => _enabledOverride = value;
    }

    public async Task<byte[]> Cached(
        string group,
        Guid ownerId,
        object parameters,
        TimeSpan ttl,
        Func<Task<byte[]>> compute,
        int version = 1,
        bool useGeneration = true,
        Func<byte[], bool>? storeIf = null)
    {
        if (!Groups.Contains(group))
        {
            throw new ArgumentException($"unknown cache group '{group}': add it to Cache.Groups");
        }
        if (!Enabled)
        {
            return await compute();
        }

        string key;
        byte[]? value;
        try
        {
            var generation = useGeneration
                ? await store.GetOrAdd(GenerationKey(ownerId), NewGeneration())
                : "none";
            key = EntryKey(group, ownerId, generation, parameters, version);
            value = await store.Get(key);
        }
        catch (Exception exc) when (IsCacheError(exc))
        {
            RecordError(group, "read", exc);
            return await compute();
        }

        if (value is not null)
        {
            Requests.WithLabels(group, "hit").Inc();
            return value;
        }
        Requests.WithLabels(group, "miss").Inc();
        value = await compute();
        if (storeIf is not null && !storeIf(value))
        {
            return value;
        }
        try
        {
            await store.Set(key, value, ttl);
        }
        catch (Exception exc) when (IsCacheError(exc))
        {
            RecordError(group, "write", exc);
        }
        return value;
    }

    /// <summary>Call only after the transaction that changed the owner's rows has committed.</summary>
    public async Task BumpOwnerGeneration(Guid ownerId)
    {
        if (!Enabled)
        {
            return;
        }
        try
        {
            await store.Set(GenerationKey(ownerId), Encoding.UTF8.GetBytes(NewGeneration()), null);
        }
        catch (Exception exc) when (IsCacheError(exc))
        {
            // The old entries stay valid until their TTL.
            RecordError(GenerationGroup, "bump", exc);
        }
    }

    static string GenerationKey(Guid ownerId) => $"generation:{ownerId}";

    static string NewGeneration() => Guid.NewGuid().ToString("N");

    internal static string EntryKey(string group, Guid ownerId, string generation, object parameters, int version)
    {
        var encoded = JsonSerializer.SerializeToUtf8Bytes(parameters, parameters.GetType());
        var digest = Convert.ToHexStringLower(SHA256.HashData(encoded));
        return $"{group}:v{version}:{ownerId}:{generation}:{digest}";
    }

    static bool IsCacheError(Exception exc) => exc is RedisException or TimeoutException or ObjectDisposedException;

    void RecordError(string group, string operation, Exception exc)
    {
        Requests.WithLabels(group, "error").Inc();
        logger.LogWarning("cache {Operation} failed for {Group}: {Error}", operation, group, exc.Message);
    }
}

/// <summary>
/// Redis, failing fast: the timeouts bound how long a failing Redis can hold up a request.
/// Connects in the background, so a Redis that is down at start-up is only a cache miss.
/// </summary>
public sealed class RedisCacheStore : ICacheStore, IDisposable
{
    // Not "instances": that prefix holds the Django version's pickled values.
    public const string KeyPrefix = "instances-net:";

    readonly Lazy<ConnectionMultiplexer> _connection;
    readonly int _database;

    public RedisCacheStore(string url)
    {
        var uri = new Uri(url);
        _database = int.TryParse(uri.AbsolutePath.Trim('/'), out var db) ? db : 0;
        var options = new ConfigurationOptions
        {
            EndPoints = { { uri.Host, uri.IsDefaultPort || uri.Port <= 0 ? 6379 : uri.Port } },
            AbortOnConnectFail = false,
            ConnectTimeout = 100,
            SyncTimeout = 100,
            AsyncTimeout = 100,
            ConnectRetry = 0,
        };
        if (uri.UserInfo.Length > 0)
        {
            var parts = uri.UserInfo.Split(':', 2);
            options.User = parts[0].Length > 0 ? Uri.UnescapeDataString(parts[0]) : null;
            options.Password = parts.Length > 1 ? Uri.UnescapeDataString(parts[1]) : null;
        }
        _connection = new Lazy<ConnectionMultiplexer>(() => ConnectionMultiplexer.Connect(options));
    }

    IDatabase Db
    {
        get
        {
            var connection = _connection.Value;
            if (!connection.IsConnected)
            {
                throw new RedisException("Redis is not connected");
            }
            return connection.GetDatabase(_database);
        }
    }

    public async Task<byte[]?> Get(string key)
    {
        var value = await Db.StringGetAsync(KeyPrefix + key);
        return value.IsNull ? null : (byte[]?)value;
    }

    public Task Set(string key, byte[] value, TimeSpan? ttl) =>
        ttl is { } expiry
            ? Db.StringSetAsync(KeyPrefix + key, value, expiry)
            : Db.StringSetAsync(KeyPrefix + key, value);

    public async Task<string> GetOrAdd(string key, string value)
    {
        var db = Db;
        await db.StringSetAsync(KeyPrefix + key, value, when: When.NotExists);
        var stored = await db.StringGetAsync(KeyPrefix + key);
        return stored.IsNull ? value : stored.ToString();
    }

    /// <summary>
    /// Every key under this service's prefix, for `clear-cache` between load-test runs: only
    /// this service's entries, never `catalog`'s or the Django version's. Not for request paths.
    /// </summary>
    public static async Task<long> Clear(string url)
    {
        using var store = new RedisCacheStore(url);
        var connection = store._connection.Value;
        long removed = 0;
        foreach (var server in connection.GetServers())
        {
            await foreach (var key in server.KeysAsync(store._database, KeyPrefix + "*", pageSize: 1000))
            {
                removed += await connection.GetDatabase(store._database).KeyDeleteAsync(key) ? 1 : 0;
            }
        }
        return removed;
    }

    public void Dispose()
    {
        if (_connection.IsValueCreated)
        {
            _connection.Value.Dispose();
        }
    }
}
