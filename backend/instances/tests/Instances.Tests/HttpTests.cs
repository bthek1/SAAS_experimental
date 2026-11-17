using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Instances.Tests.Support;

namespace Instances.Tests;

/// <summary>An owner with a type, a battery type and some rows, made through the API.</summary>
sealed class Seed
{
    public required Guid OwnerId { get; init; }
    public required HttpClient Owner { get; init; }
    public required Guid TypeId { get; init; }
    public required Guid BatteryTypeId { get; init; }

    public static async Task<Seed> Create(TestApp app)
    {
        var ownerId = Guid.NewGuid();
        var typeId = Guid.NewGuid();
        var batteryTypeId = Guid.NewGuid();
        var scored = new { pages = Array.Empty<object>(), calculatedValues = new[] { new { name = "total", title = "Total" } } };
        await app.Send(Events.QuestionnaireType(ownerId, typeId, json: scored));
        await app.Send(Events.BatteryType(ownerId, batteryTypeId, [typeId, typeId]));
        return new Seed { OwnerId = ownerId, Owner = app.Owner(ownerId), TypeId = typeId, BatteryTypeId = batteryTypeId };
    }

    /// <summary>
    /// `count` questionnaires and as many two-slot batteries (three questionnaires a row),
    /// half of the standalone ones submitted.
    /// </summary>
    public async Task AddRows(TestApp app, int count)
    {
        for (var i = 0; i < count; i++)
        {
            var created = await Json(await Owner.PostAsJsonAsync("/api/questionnaires/", new { questionnaireTypeId = TypeId, name = $"r{i}" }));
            await Json(await Owner.PostAsJsonAsync("/api/batteries/", new { batteryTypeId = BatteryTypeId }));
            if (i % 2 == 0)
            {
                var anonymous = app.Client;
                var token = created.GetProperty("shareToken").GetString();
                var submitted = await anonymous.PatchAsJsonAsync($"/api/questionnaires/by-token/{token}/submit/",
                    new { answers = new { q1 = "a" }, metrics = new { total = i } });
                Assert.Equal(HttpStatusCode.OK, submitted.StatusCode);
            }
        }
    }

    public static async Task<JsonElement> Json(HttpResponseMessage response)
    {
        var body = await response.Content.ReadAsStringAsync();
        Assert.True(response.IsSuccessStatusCode, $"{(int)response.StatusCode}: {body}");
        return JsonDocument.Parse(body).RootElement.Clone();
    }
}

/// <summary>Hot paths cost a fixed number of queries, however many rows the owner has (#9).</summary>
[Trait("Category", "QueryCounts")]
public sealed class QueryCountTests(Postgres postgres) : IAsyncLifetime
{
    TestApp _app = null!;
    Seed _seed = null!;

    public async ValueTask InitializeAsync()
    {
        _app = await TestApp.Start(postgres);
        _seed = await Seed.Create(_app);
    }

    public async ValueTask DisposeAsync() => await _app.DisposeAsync();

    async Task<int> Count(Func<Task<HttpResponseMessage>> request)
    {
        _app.Commands.Reset();
        var response = await request();
        Assert.True(response.IsSuccessStatusCode, await response.Content.ReadAsStringAsync());
        return _app.Commands.Count;
    }

    async Task<Dictionary<string, int>> Measure()
    {
        var created = await Seed.Json(await _seed.Owner.PostAsJsonAsync("/api/questionnaires/", new { questionnaireTypeId = _seed.TypeId }));
        var id = created.GetProperty("id").GetString();
        var token = created.GetProperty("shareToken").GetString();
        return new Dictionary<string, int>
        {
            ["questionnaire-list"] = await Count(() => _seed.Owner.GetAsync("/api/questionnaires/")),
            ["questionnaire-detail"] = await Count(() => _seed.Owner.GetAsync($"/api/questionnaires/{id}/")),
            ["battery-list"] = await Count(() => _seed.Owner.GetAsync("/api/batteries/")),
            ["respondent-read"] = await Count(() => _app.Client.GetAsync($"/api/questionnaires/by-token/{token}/")),
            ["respondent-submit"] = await Count(() => _app.Client.PatchAsJsonAsync(
                $"/api/questionnaires/by-token/{token}/submit/", new { answers = new { q1 = "a" } })),
            ["dashboard"] = await Count(() => _seed.Owner.GetAsync("/api/dashboard/?days=30&tz=Australia/Sydney")),
            ["dashboard-scores"] = await Count(() => _seed.Owner.GetAsync($"/api/dashboard/scores/?questionnaireType={_seed.TypeId}")),
        };
    }

    [Fact]
    public async Task Counts_do_not_grow_with_rows()
    {
        await _seed.AddRows(_app, 3);
        var few = await Measure();
        await _seed.AddRows(_app, 30);
        var many = await Measure();
        Assert.Equal(few, many);
        // Each authenticated request pays one query for the blocked-owner check, no more.
        Assert.Equal(3, few["questionnaire-list"]);
        Assert.Equal(2, few["questionnaire-detail"]);
    }
}

/// <summary>The cache's rules (#11), through the real endpoints.</summary>
[Trait("Category", "Cache")]
public sealed class CacheTests(Postgres postgres) : IAsyncLifetime
{
    TestApp _app = null!;

    public async ValueTask InitializeAsync() => _app = await TestApp.Start(postgres, cacheEnabled: true);

    public async ValueTask DisposeAsync() => await _app.DisposeAsync();

    static async Task<int> Sent(HttpClient owner) =>
        (await Seed.Json(await owner.GetAsync("/api/dashboard/"))).GetProperty("kpis").GetProperty("questionnairesSent").GetInt32();

    [Fact]
    public async Task Two_owners_never_share_a_value()
    {
        var one = await Seed.Create(_app);
        var two = await Seed.Create(_app);
        await one.AddRows(_app, 2);
        Assert.Equal(6, await Sent(one.Owner));
        Assert.Equal(0, await Sent(two.Owner));
        Assert.Equal(6, await Sent(one.Owner));
        Assert.All(_app.Store.Keys.Where(k => k.StartsWith("dashboard:")), key =>
            Assert.True(key.Contains(one.OwnerId.ToString()) || key.Contains(two.OwnerId.ToString())));
    }

    [Fact]
    public async Task A_hit_is_served_until_a_delete_bumps_the_generation()
    {
        var seed = await Seed.Create(_app);
        var created = await Seed.Json(await seed.Owner.PostAsJsonAsync("/api/questionnaires/", new { questionnaireTypeId = seed.TypeId }));
        Assert.Equal(1, await Sent(seed.Owner));
        // Creation does not invalidate: dashboards lag new rows by up to the TTL.
        await seed.Owner.PostAsJsonAsync("/api/questionnaires/", new { questionnaireTypeId = seed.TypeId });
        await seed.Owner.PostAsJsonAsync("/api/questionnaires/", new { questionnaireTypeId = seed.TypeId });
        Assert.Equal(1, await Sent(seed.Owner));
        // A delete does: three made, one gone.
        Assert.Equal(HttpStatusCode.NoContent, (await seed.Owner.DeleteAsync($"/api/questionnaires/{created.GetProperty("id")}/")).StatusCode);
        Assert.Equal(2, await Sent(seed.Owner));
    }

    [Fact]
    public async Task A_dead_redis_still_answers()
    {
        var seed = await Seed.Create(_app);
        await seed.AddRows(_app, 1);
        _app.Store.Down = true;
        Assert.Equal(3, await Sent(seed.Owner));
        Assert.Equal(HttpStatusCode.OK, (await seed.Owner.GetAsync($"/api/dashboard/scores/?questionnaireType={seed.TypeId}")).StatusCode);
    }

    [Fact]
    public async Task A_blocked_owner_is_refused_even_on_a_hit()
    {
        var seed = await Seed.Create(_app);
        Assert.Equal(0, await Sent(seed.Owner));
        await _app.Send(Events.User("deactivated", seed.OwnerId, 1));
        Assert.Equal(HttpStatusCode.Unauthorized, (await seed.Owner.GetAsync("/api/dashboard/")).StatusCode);
    }

    [Fact]
    public async Task Off_means_nothing_is_stored()
    {
        _app.Service<Instances.Api.Caching.Cache>().Enabled = false;
        try
        {
            var seed = await Seed.Create(_app);
            await Sent(seed.Owner);
            Assert.DoesNotContain(_app.Store.Keys, key => key.StartsWith("dashboard:"));
        }
        finally
        {
            _app.Service<Instances.Api.Caching.Cache>().Enabled = true;
        }
    }
}
