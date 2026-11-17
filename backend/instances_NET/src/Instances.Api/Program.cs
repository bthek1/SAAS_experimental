using Instances.Api.Auth;
using Instances.Api.Caching;
using Instances.Api.Commands;
using Instances.Api.Config;
using Instances.Api.Dashboard;
using Instances.Api.Data;
using Instances.Api.Http;
using Instances.Api.Peers;
using Instances.Api.Refs;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.HostFiltering;
using Microsoft.EntityFrameworkCore;
using Prometheus;

namespace Instances.Api;

/// <summary>
/// `instances` on ASP.NET Core (#42). With no arguments it serves HTTP; otherwise the first
/// argument is a command (`migrate`), as the Django version had commands.
/// </summary>
public static class Program
{
    public static async Task<int> Main(string[] args)
    {
        if (args is ["health", ..])
        {
            return await Health(args.Length > 1 ? args[1] : "http://127.0.0.1:8000/internal/health/");
        }
        Settings settings;
        try
        {
            settings = Settings.Load();
        }
        catch (SettingsException exc)
        {
            await Console.Error.WriteLineAsync($"instances: {exc.Message}");
            return 2;
        }

        if (args.Length > 0 && !args[0].StartsWith('-'))
        {
            return await Cli.Run(args, settings);
        }
        // A tuning knob for the LXC deploy (#44): threads ready before the pool grows.
        if (int.TryParse(Environment.GetEnvironmentVariable("THREADPOOL_MIN_THREADS"), out var minThreads) && minThreads > 0)
        {
            ThreadPool.SetMinThreads(minThreads, minThreads);
        }
        var app = Build(args, settings);
        await app.RunAsync();
        return 0;
    }

    public const int KeepAliveSeconds = 75;

    /// <summary>A container health check: the runtime image has no curl or Python.</summary>
    static async Task<int> Health(string url)
    {
        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
            using var response = await http.GetAsync(url);
            return response.IsSuccessStatusCode ? 0 : 1;
        }
        catch (Exception exc) when (exc is HttpRequestException or TaskCanceledException)
        {
            return 1;
        }
    }

    /// <param name="configure">Tests swap services here, after the real ones are added.</param>
    public static WebApplication Build(string[] args, Settings settings, Action<WebApplicationBuilder>? configure = null)
    {
        var builder = WebApplication.CreateBuilder(new WebApplicationOptions { Args = args });
        builder.Logging.AddFilter("Microsoft.EntityFrameworkCore.Database.Command", LogLevel.Warning);
        // Longer than the gateway keeps an idle upstream connection, or a request can
        // arrive just as Kestrel closes it: a 502 (#24, tests/test_kestrel_keepalive.py).
        builder.WebHost.ConfigureKestrel(kestrel =>
            kestrel.Limits.KeepAliveTimeout = TimeSpan.FromSeconds(KeepAliveSeconds));
        AddServices(builder.Services, settings);
        configure?.Invoke(builder);

        var app = builder.Build();
        app.UseMiddleware<MetricsEndpoint>();
        app.UseHostFiltering();
        if (settings.HttpsRedirect)
        {
            // Between the services is a private network: /internal/ stays plain HTTP.
            app.UseWhen(context => !context.Request.Path.StartsWithSegments("/internal"), branch =>
            {
                branch.UseHttpsRedirection();
                branch.UseHsts();
            });
        }
        app.UseRouting();
        app.UseMiddleware<RequestMetrics>();
        app.UseCors();
        app.UseAuthentication();
        app.UseAuthorization();
        app.MapControllers();
        return app;
    }

    public static void AddServices(IServiceCollection services, Settings settings)
    {
        services.AddSingleton(settings);
        services.AddSingleton<Microsoft.EntityFrameworkCore.Diagnostics.IInterceptor, DbMetrics>();
        services.AddDbContextPool<InstancesDb>((provider, options) => options
            .UseNpgsql(DatabaseUrl.ToConnectionString(settings.DatabaseUrl, settings.DatabasePoolSize))
            // Query-count tests add a command counter here.
            .AddInterceptors(provider.GetServices<Microsoft.EntityFrameworkCore.Diagnostics.IInterceptor>()));

        services.AddSingleton<ICacheStore>(_ => new RedisCacheStore(settings.CacheRedisUrl));
        services.AddSingleton<Cache>();

        services.AddHttpClient<ICatalogClient, HttpCatalogClient>(http => HttpCatalogClient.Configure(http, settings))
            .ConfigurePrimaryHttpMessageHandler(() => HttpCatalogClient.Handler(settings));
        services.AddScoped<RefService>();
        services.AddScoped<OwnedRefs>();
        services.AddScoped<DashboardService>();

        services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
            .AddJwtBearer(options => OwnerAuth.Configure(options, settings));
        services.AddAuthorization();

        services.Configure<HostFilteringOptions>(options =>
        {
            options.AllowedHosts = settings.AllowedHosts.ToList();
            options.AllowEmptyHosts = false;
            options.IncludeFailureMessage = false;
        });
        services.AddCors(options => options.AddDefaultPolicy(policy => policy
            .SetIsOriginAllowed(origin =>
                settings.CorsAllowedOrigins.Contains(origin)
                || settings.CorsAllowedOriginPatterns.Any(pattern => pattern.IsMatch(origin)))
            .AllowAnyHeader()
            .AllowAnyMethod()
            // Lets the SPA, another origin, read the filename of a PDF download.
            .WithExposedHeaders("Content-Disposition")));

        // Named, since a test host's entry assembly is not this one.
        services.AddControllers(options => options.Filters.Add<ApiExceptionFilter>())
            .AddApplicationPart(typeof(Program).Assembly);
    }
}

/// <summary>Verbs of the service binary, as the Django version had commands.</summary>
public static class Cli
{
    public static async Task<int> Run(string[] args, Settings settings)
    {
        var services = new ServiceCollection();
        // EF logs its probe for a history table that does not exist yet as a failure.
        // stdout is the command's output: warnings and errors only.
        services.AddLogging(logging => logging.AddSimpleConsole()
            .SetMinimumLevel(LogLevel.Warning)
            .AddFilter("Microsoft.EntityFrameworkCore.Database.Command", LogLevel.None));
        Program.AddServices(services, settings);
        await using var provider = services.BuildServiceProvider();
        await using var scope = provider.CreateAsyncScope();
        var scoped = scope.ServiceProvider;
        var db = scoped.GetRequiredService<InstancesDb>();
        var options = Options(args.Skip(1));
        switch (args[0])
        {
            case "migrate":
                Console.WriteLine(await Schema.Migrate(db));
                return 0;
            case "seed-loadtest":
                if (!(settings.Debug || settings.LoadTest))
                {
                    await Console.Error.WriteLineAsync("instances: seed-loadtest runs only under dev or loadtest.");
                    return 1;
                }
                var result = await new Seeding(db).Seed(
                    int.Parse(options.GetValueOrDefault("questionnaires-per-owner", "200"), System.Globalization.CultureInfo.InvariantCulture),
                    int.Parse(options.GetValueOrDefault("seed", "1234"), System.Globalization.CultureInfo.InvariantCulture));
                Console.WriteLine($"owners: {result.OwnersSeeded} seeded, {result.OwnersSkipped} already there");
                Console.WriteLine($"batteries: {result.Batteries}, questionnaires: {result.Questionnaires} ({result.Submitted} submitted)");
                return 0;
            case "reset-db":
                if (!(settings.Debug || settings.LoadTest))
                {
                    await Console.Error.WriteLineAsync("instances: reset-db runs only under dev or loadtest.");
                    return 1;
                }
                // `just loadtest-reset`: every measured run starts from the same, empty data.
                await db.Database.ExecuteSqlRawAsync("""
                    TRUNCATE questionnaires_questionnaire, questionnaires_battery, questionnaires_batterytyperefslot,
                        questionnaires_batterytyperef, questionnaires_questionnairetyperef, questionnaires_retiredref,
                        questionnaires_blockedowner RESTART IDENTITY
                    """);
                Console.WriteLine("emptied every questionnaires_ table");
                return 0;
            case "clear-cache":
                if (!(settings.Debug || settings.LoadTest))
                {
                    await Console.Error.WriteLineAsync("instances: clear-cache runs only under dev or loadtest.");
                    return 1;
                }
                Console.WriteLine($"removed {await RedisCacheStore.Clear(settings.CacheRedisUrl)} keys");
                return 0;
            case "reconcile-refs":
                var report = await new Reconcile(db, scoped.GetRequiredService<RefService>(),
                    scoped.GetRequiredService<ICatalogClient>()).Run(dryRun: options.ContainsKey("dry-run"));
                foreach (var (name, rows) in report.Sections)
                {
                    Console.WriteLine($"{name}: {rows.Count}");
                    foreach (var row in rows)
                    {
                        Console.WriteLine($"  {row}");
                    }
                }
                return 0;
            default:
                await Console.Error.WriteLineAsync(
                    $"instances: unknown command '{args[0]}'. Commands: migrate, seed-loadtest, reconcile-refs, reset-db, clear-cache, health");
                return 2;
        }
    }

    /// <summary>`--name value`, `--name=value`, or a bare `--flag`.</summary>
    static Dictionary<string, string> Options(IEnumerable<string> args)
    {
        var options = new Dictionary<string, string>();
        string? pending = null;
        foreach (var arg in args)
        {
            if (arg.StartsWith("--", StringComparison.Ordinal))
            {
                if (pending is not null)
                {
                    options[pending] = "";
                }
                var parts = arg[2..].Split('=', 2);
                if (parts.Length == 2)
                {
                    options[parts[0]] = parts[1];
                    pending = null;
                }
                else
                {
                    pending = parts[0];
                }
            }
            else if (pending is not null)
            {
                options[pending] = arg;
                pending = null;
            }
        }
        if (pending is not null)
        {
            options[pending] = "";
        }
        return options;
    }
}
