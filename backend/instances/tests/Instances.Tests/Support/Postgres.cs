using Instances.Api.Data;
using Microsoft.EntityFrameworkCore;
using Npgsql;
using Testcontainers.PostgreSql;

[assembly: AssemblyFixture(typeof(Instances.Tests.Support.Postgres))]

namespace Instances.Tests.Support;

/// <summary>
/// One throwaway Postgres for the whole run (#42 is Postgres only: the dashboard's date
/// and time-zone SQL is what most needs a real database). Each test class takes a fresh
/// database in it, built by the same migration the service runs.
/// </summary>
public sealed class Postgres : IAsyncLifetime
{
    readonly PostgreSqlContainer _container = new PostgreSqlBuilder("postgres:16-alpine")
        .WithTmpfsMount("/var/lib/postgresql/data")
        .Build();

    public async ValueTask InitializeAsync() => await _container.StartAsync();

    public async ValueTask DisposeAsync() => await _container.DisposeAsync();

    /// <summary>A new, migrated database, as a `postgres://` URL the service reads.</summary>
    public async Task<string> NewDatabase()
    {
        var name = "t_" + Guid.NewGuid().ToString("N")[..12];
        await using (var connection = new NpgsqlConnection(_container.GetConnectionString()))
        {
            await connection.OpenAsync();
            await using var create = new NpgsqlCommand($"CREATE DATABASE {name}", connection);
            await create.ExecuteNonQueryAsync();
        }
        var url = Url(name);
        await using var db = Context(url);
        await Schema.Migrate(db);
        return url;
    }

    public string Url(string database)
    {
        var builder = new NpgsqlConnectionStringBuilder(_container.GetConnectionString());
        return $"postgres://{builder.Username}:{builder.Password}@{builder.Host}:{builder.Port}/{database}";
    }

    public static InstancesDb Context(string url) => new(
        new DbContextOptionsBuilder<InstancesDb>()
            .UseNpgsql(DatabaseUrl.ToConnectionString(url, 5))
            .Options);
}
