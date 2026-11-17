using System.Collections.Concurrent;
using System.Data.Common;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using Instances.Api;
using Instances.Api.Caching;
using Instances.Api.Config;
using Instances.Api.Data;
using Instances.Api.Peers;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.TestHost;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Tokens;
using StackExchange.Redis;

namespace Instances.Tests.Support;

/// <summary>
/// The real pipeline on a TestServer, on its own database, with the cache in memory,
/// `catalog` faked, and every SQL command counted.
/// </summary>
public sealed class TestApp : IAsyncDisposable
{
    public const string PeerToken = "test-catalog-to-instances";

    public required WebApplication App { get; init; }
    public required HttpClient Client { get; init; }
    public required MemoryCacheStore Store { get; init; }
    public required FakeCatalog Catalog { get; init; }
    public required CommandCounter Commands { get; init; }
    public required string DatabaseUrl { get; init; }

    public static async Task<TestApp> Start(Postgres postgres, bool cacheEnabled = false)
    {
        var url = await postgres.NewDatabase();
        var settings = Settings.Load(new Dictionary<string, string>
        {
            ["SETTINGS"] = "test",
            ["INSTANCES_DATABASE_URL"] = url,
        }) with
        { CacheEnabled = cacheEnabled };
        var store = new MemoryCacheStore();
        var catalog = new FakeCatalog();
        var commands = new CommandCounter();
        var app = Program.Build([], settings, builder =>
        {
            builder.WebHost.UseTestServer();
            builder.Logging.ClearProviders();
            builder.Services.AddSingleton<ICacheStore>(store);
            builder.Services.AddSingleton<ICatalogClient>(catalog);
            builder.Services.AddSingleton<IInterceptor>(commands);
        });
        await app.StartAsync();
        return new TestApp
        {
            App = app,
            Client = app.GetTestClient(),
            Store = store,
            Catalog = catalog,
            Commands = commands,
            DatabaseUrl = url,
        };
    }

    public InstancesDb Db() => Postgres.Context(DatabaseUrl);

    public T Service<T>() where T : notnull => App.Services.GetRequiredService<T>();

    /// <summary>A client for one owner, with a token as `catalog` issues it.</summary>
    public HttpClient Owner(Guid ownerId)
    {
        var client = App.GetTestClient();
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", Tokens.Access(ownerId));
        return client;
    }

    public async Task<string> Send(object @event)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, "/internal/events/")
        {
            Content = JsonContent.Create(@event),
        };
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", PeerToken);
        using var response = await Client.SendAsync(request);
        var body = await response.Content.ReadAsStringAsync();
        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"{(int)response.StatusCode}: {body}");
        }
        return JsonDocument.Parse(body).RootElement.GetProperty("result").GetString()!;
    }

    public async ValueTask DisposeAsync()
    {
        Client.Dispose();
        await App.DisposeAsync();
    }
}

public static class Events
{
    public static string Stamp(DateTime? moment = null) =>
        (moment ?? DateTime.UtcNow).ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'+00:00'");

    public static object QuestionnaireType(Guid ownerId, Guid id, long version = 1, string title = "PHQ-9", object? json = null) => new
    {
        id = Guid.NewGuid(),
        type = "questionnaire_type.changed",
        aggregateId = id,
        version,
        data = new
        {
            ownerId,
            title,
            createdAt = Stamp(),
            updatedAt = Stamp(),
            questionnaireJson = json ?? new { pages = Array.Empty<object>() },
        },
    };

    public static object BatteryType(Guid ownerId, Guid id, IEnumerable<Guid> slots, long version = 1, string title = "Intake") => new
    {
        id = Guid.NewGuid(),
        type = "battery_type.changed",
        aggregateId = id,
        version,
        data = new
        {
            ownerId,
            title,
            createdAt = Stamp(),
            updatedAt = Stamp(),
            description = "",
            items = slots.Select((qtype, order) => new { questionnaireTypeId = qtype, order }).ToArray(),
        },
    };

    public static object User(string action, Guid ownerId, long version) => new
    {
        id = Guid.NewGuid(),
        type = $"user.{action}",
        aggregateId = ownerId,
        version,
        data = new { },
    };

    public static JsonElement Json(object value) => JsonSerializer.SerializeToElement(value);
}

/// <summary>Access tokens signed with the published dev key, read from `common/dev_keys.py`.</summary>
public static class Tokens
{
    static readonly Lazy<RsaSecurityKey> Key = new(() =>
    {
        var source = File.ReadAllText(Paths.Backend("common", "common", "dev_keys.py"));
        var pem = Regex.Match(source, "DEV_SIGNING_KEY = \"\"\"(?<pem>.*?)\"\"\"", RegexOptions.Singleline).Groups["pem"].Value;
        var rsa = RSA.Create();
        rsa.ImportFromPem(pem);
        return new RsaSecurityKey(rsa);
    });

    public static string Access(Guid ownerId, string tokenType = "access") => new JsonWebTokenHandler().CreateToken(
        new SecurityTokenDescriptor
        {
            Claims = new Dictionary<string, object>
            {
                ["token_type"] = tokenType,
                ["jti"] = Guid.NewGuid().ToString("N"),
                ["user_id"] = ownerId.ToString(),
            },
            Expires = DateTime.UtcNow.AddMinutes(5),
            SigningCredentials = new SigningCredentials(Key.Value, SecurityAlgorithms.RsaSha256),
        });
}

public static class Paths
{
    /// <summary>A path under `backend/`, found from the test binary.</summary>
    public static string Backend(params string[] parts)
    {
        for (var dir = new DirectoryInfo(AppContext.BaseDirectory); dir is not null; dir = dir.Parent)
        {
            if (Directory.Exists(Path.Combine(dir.FullName, "contracts")) && Directory.Exists(Path.Combine(dir.FullName, "common")))
            {
                return Path.Combine([dir.FullName, .. parts]);
            }
        }
        throw new DirectoryNotFoundException("backend/ not found above the test binary");
    }
}

/// <summary>Redis's role, in memory. `Down` makes every call fail as a dead Redis would.</summary>
public sealed class MemoryCacheStore : ICacheStore
{
    readonly ConcurrentDictionary<string, byte[]> _values = new();

    public bool Down { get; set; }
    public IReadOnlyCollection<string> Keys => _values.Keys.ToList();

    void Check()
    {
        if (Down)
        {
            throw new RedisException("down");
        }
    }

    public Task<byte[]?> Get(string key)
    {
        Check();
        return Task.FromResult(_values.TryGetValue(key, out var value) ? value : null);
    }

    public Task Set(string key, byte[] value, TimeSpan? ttl)
    {
        Check();
        _values[key] = value;
        return Task.CompletedTask;
    }

    public Task<string> GetOrAdd(string key, string value)
    {
        Check();
        return Task.FromResult(System.Text.Encoding.UTF8.GetString(
            _values.GetOrAdd(key, System.Text.Encoding.UTF8.GetBytes(value))));
    }
}

/// <summary>What `catalog` would answer. Unknown ids are a 404; `Down` is no answer at all.</summary>
public sealed class FakeCatalog : ICatalogClient
{
    public ConcurrentDictionary<Guid, JsonElement> Types { get; } = new();
    public bool Down { get; set; }
    public int Calls;

    public Task<JsonElement?> Fetch(string kind, Guid refId)
    {
        Interlocked.Increment(ref Calls);
        if (Down)
        {
            throw new PeerUnavailable("catalog is down");
        }
        return Task.FromResult(Types.TryGetValue(refId, out var snapshot) ? snapshot : (JsonElement?)null);
    }

    public async IAsyncEnumerable<JsonElement> Snapshots(string kind)
    {
        await Task.Yield();
        foreach (var snapshot in Types.Values.Where(s => s.GetProperty("type").GetString() == $"{kind}.changed"))
        {
            yield return snapshot;
        }
    }
}

/// <summary>Counts every SQL command EF sends.</summary>
public sealed class CommandCounter : DbCommandInterceptor
{
    int _count;

    public int Count => _count;

    public void Reset() => Interlocked.Exchange(ref _count, 0);

    public override ValueTask<InterceptionResult<DbDataReader>> ReaderExecutingAsync(
        DbCommand command, CommandEventData eventData, InterceptionResult<DbDataReader> result, CancellationToken cancellationToken = default)
    {
        Interlocked.Increment(ref _count);
        return base.ReaderExecutingAsync(command, eventData, result, cancellationToken);
    }

    public override ValueTask<InterceptionResult<int>> NonQueryExecutingAsync(
        DbCommand command, CommandEventData eventData, InterceptionResult<int> result, CancellationToken cancellationToken = default)
    {
        Interlocked.Increment(ref _count);
        return base.NonQueryExecutingAsync(command, eventData, result, cancellationToken);
    }

    public override ValueTask<InterceptionResult<object>> ScalarExecutingAsync(
        DbCommand command, CommandEventData eventData, InterceptionResult<object> result, CancellationToken cancellationToken = default)
    {
        Interlocked.Increment(ref _count);
        return base.ScalarExecutingAsync(command, eventData, result, cancellationToken);
    }
}
