using System.Text.Json;
using Instances.Api.Caching;
using Instances.Api.Data;
using Instances.Api.Refs;
using Instances.Tests.Support;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Instances.Tests;

/// <summary>Copies of `catalog`'s types, and every way they change (#13, `refs.py`'s rules).</summary>
[Trait("Category", "Refs")]
public sealed class RefTests(Postgres postgres) : IAsyncLifetime
{
    TestApp _app = null!;

    public async ValueTask InitializeAsync() => _app = await TestApp.Start(postgres, cacheEnabled: true);

    public async ValueTask DisposeAsync() => await _app.DisposeAsync();

    async Task<T> InScope<T>(Func<RefService, Task<T>> action)
    {
        await using var scope = _app.App.Services.CreateAsyncScope();
        return await action(scope.ServiceProvider.GetRequiredService<RefService>());
    }

    Task<string> Apply(object @event) => InScope(refs => refs.ApplyEvent(Events.Json(@event)));

    async Task<string?> Generation(Guid ownerId) =>
        (await _app.Store.Get($"generation:{ownerId}")) is { } value ? System.Text.Encoding.UTF8.GetString(value) : null;

    [Fact]
    public async Task An_event_applies_once_and_an_older_one_is_ignored()
    {
        var owner = Guid.NewGuid();
        var id = Guid.NewGuid();
        Assert.Equal("applied", await Apply(Events.QuestionnaireType(owner, id, 2, "Two")));
        Assert.Equal("ignored", await Apply(Events.QuestionnaireType(owner, id, 2, "Again")));
        Assert.Equal("ignored", await Apply(Events.QuestionnaireType(owner, id, 1, "One")));
        Assert.Equal("applied", await Apply(Events.QuestionnaireType(owner, id, 3, "Three")));
        await using var db = _app.Db();
        var copy = await db.QuestionnaireTypeRefs.SingleAsync(t => t.Id == id);
        Assert.Equal(("Three", 3L), (copy.Title, copy.Version));
    }

    [Fact]
    public async Task Applying_bumps_the_owners_generation_after_the_commit()
    {
        var owner = Guid.NewGuid();
        await _app.Store.GetOrAdd($"generation:{owner}", "before");
        await Apply(Events.QuestionnaireType(owner, Guid.NewGuid()));
        Assert.NotEqual("before", await Generation(owner));
    }

    [Fact]
    public async Task An_event_that_fails_in_its_transaction_bumps_nothing_and_stores_nothing()
    {
        var owner = Guid.NewGuid();
        var id = Guid.NewGuid();
        await _app.Store.GetOrAdd($"generation:{owner}", "before");
        // Two slots at one order break a unique constraint, after the copy was written.
        var broken = Events.BatteryType(owner, id, []);
        var json = JsonSerializer.SerializeToNode(broken)!;
        var slot = new { questionnaireTypeId = Guid.NewGuid(), order = 0 };
        json["data"]!["items"] = JsonSerializer.SerializeToNode(new[] { slot, slot });
        await Assert.ThrowsAnyAsync<Exception>(() => InScope(refs => refs.ApplyEvent(JsonSerializer.SerializeToElement(json))));
        Assert.Equal("before", await Generation(owner));
        await using var db = _app.Db();
        Assert.False(await db.BatteryTypeRefs.AnyAsync(t => t.Id == id));
    }

    [Fact]
    public async Task Two_concurrent_events_for_one_type_leave_the_higher_version()
    {
        var owner = Guid.NewGuid();
        for (var round = 0; round < 10; round++)
        {
            var id = Guid.NewGuid();
            var results = await Task.WhenAll(
                Apply(Events.QuestionnaireType(owner, id, 2, "Two")),
                Apply(Events.QuestionnaireType(owner, id, 3, "Three")));
            await using var db = _app.Db();
            var copy = await db.QuestionnaireTypeRefs.SingleAsync(t => t.Id == id);
            Assert.Equal(("Three", 3L), (copy.Title, copy.Version));
            Assert.Contains("applied", results);
        }
    }

    [Fact]
    public async Task A_battery_types_slots_follow_its_latest_event()
    {
        var owner = Guid.NewGuid();
        var id = Guid.NewGuid();
        Guid a = Guid.NewGuid(), b = Guid.NewGuid();
        await Apply(Events.BatteryType(owner, id, [a, b], 1));
        await Apply(Events.BatteryType(owner, id, [b, a, b], 2));
        await using var db = _app.Db();
        var slots = await db.BatteryTypeRefSlots.Where(s => s.BatteryTypeId == id).OrderBy(s => s.Order)
            .Select(s => s.QuestionnaireTypeId).ToListAsync();
        Assert.Equal([b, a, b], slots);
    }

    [Fact]
    public async Task Retire_leaves_a_tombstone_that_no_late_event_undoes()
    {
        var owner = Guid.NewGuid();
        var id = Guid.NewGuid();
        await Apply(Events.QuestionnaireType(owner, id));
        await InScope(async refs => { await refs.Retire(Kinds.QuestionnaireType, id); return 0; });
        Assert.Equal("ignored", await Apply(Events.QuestionnaireType(owner, id, 9)));
        await using var db = _app.Db();
        Assert.False(await db.QuestionnaireTypeRefs.AnyAsync(t => t.Id == id));
        Assert.True(await db.RetiredRefs.AnyAsync(r => r.RefId == id));
    }

    [Fact]
    public async Task A_type_in_use_cannot_be_retired()
    {
        var owner = Guid.NewGuid();
        var id = Guid.NewGuid();
        await Apply(Events.QuestionnaireType(owner, id));
        await using (var db = _app.Db())
        {
            db.Questionnaires.Add(new Questionnaire
            {
                Id = Guid.NewGuid(),
                OwnerId = owner,
                QuestionnaireTypeId = id,
                ShareToken = Guid.NewGuid(),
                CreatedAt = DateTime.UtcNow,
                UpdatedAt = DateTime.UtcNow,
            });
            await db.SaveChangesAsync();
        }
        await Assert.ThrowsAsync<RefInUse>(() => InScope(async refs => { await refs.Retire(Kinds.QuestionnaireType, id); return 0; }));
        await using var check = _app.Db();
        Assert.True(await check.QuestionnaireTypeRefs.AnyAsync(t => t.Id == id));
        Assert.False(await check.RetiredRefs.AnyAsync(r => r.RefId == id));
    }

    [Fact]
    public async Task A_snapshot_from_catalog_clears_a_tombstone()
    {
        var owner = Guid.NewGuid();
        var id = Guid.NewGuid();
        await InScope(async refs => { await refs.Retire(Kinds.QuestionnaireType, id); return 0; });
        _app.Catalog.Types[id] = Events.Json(Events.QuestionnaireType(owner, id, 4, "Back"));
        Assert.True(await InScope(refs => refs.ReadThrough(Kinds.QuestionnaireType, id)));
        await using var db = _app.Db();
        Assert.False(await db.RetiredRefs.AnyAsync(r => r.RefId == id));
        Assert.Equal("Back", (await db.QuestionnaireTypeRefs.SingleAsync(t => t.Id == id)).Title);
    }

    [Fact]
    public async Task User_events_block_unblock_and_delete()
    {
        var owner = Guid.NewGuid();
        var id = Guid.NewGuid();
        await Apply(Events.QuestionnaireType(owner, id));
        Assert.Equal("applied", await Apply(Events.User("deactivated", owner, 1)));
        Assert.Equal("applied", await Apply(Events.User("reactivated", owner, 2)));
        Assert.Equal("ignored", await Apply(Events.User("deactivated", owner, 1)));
        Assert.Equal("applied", await Apply(Events.User("deleted", owner, 3)));
        Assert.Equal("ignored", await Apply(Events.User("reactivated", owner, 9)));
        // A late type event for a deleted owner brings nothing back.
        Assert.Equal("ignored", await Apply(Events.QuestionnaireType(owner, Guid.NewGuid())));
        await using var db = _app.Db();
        var row = await db.BlockedOwners.SingleAsync(b => b.OwnerId == owner);
        Assert.True(row.Blocked && row.Deleted);
        Assert.False(await db.QuestionnaireTypeRefs.AnyAsync(t => t.OwnerId == owner));
    }

    [Theory]
    [InlineData("""{"type": "nonsense.thing", "aggregateId": "x", "version": 1, "data": {}}""")]
    [InlineData("""{"aggregateId": "x", "version": 1, "data": {}}""")]
    [InlineData("""{"type": "questionnaire_type.changed", "aggregateId": "00000000-0000-0000-0000-000000000001", "version": "2", "data": {}}""")]
    [InlineData("""[]""")]
    public async Task A_malformed_event_is_a_bad_event(string body) =>
        await Assert.ThrowsAsync<BadEvent>(() => InScope(refs => refs.ApplyEvent(JsonDocument.Parse(body).RootElement)));
}

/// <summary>`backend/contracts/`: what `catalog` sends must be accepted as it is.</summary>
[Trait("Category", "Refs")]
public sealed class ContractTests(Postgres postgres) : IAsyncLifetime
{
    TestApp _app = null!;

    public async ValueTask InitializeAsync() => _app = await TestApp.Start(postgres);

    public async ValueTask DisposeAsync() => await _app.DisposeAsync();

    static JsonElement Contract(string name) =>
        JsonDocument.Parse(File.ReadAllText(Paths.Backend("contracts", $"{name}.json"))).RootElement.Clone();

    [Theory]
    [InlineData("event.questionnaire_type.changed")]
    [InlineData("event.battery_type.changed")]
    [InlineData("event.user.deactivated")]
    public async Task An_event_contract_is_applied(string name)
    {
        await using var scope = _app.App.Services.CreateAsyncScope();
        var refs = scope.ServiceProvider.GetRequiredService<RefService>();
        Assert.Equal("applied", await refs.ApplyEvent(Contract(name)));
    }

    [Fact]
    public async Task The_event_contracts_apply_in_the_order_catalog_sends_them()
    {
        await using var scope = _app.App.Services.CreateAsyncScope();
        var refs = scope.ServiceProvider.GetRequiredService<RefService>();
        foreach (var name in new[]
        {
            "event.questionnaire_type.changed", "event.battery_type.changed", "event.battery_type.deleted",
            "event.questionnaire_type.deleted", "event.user.deactivated", "event.user.reactivated", "event.user.deleted",
        })
        {
            Assert.Equal("applied", await refs.ApplyEvent(Contract(name)));
        }
    }

    [Theory]
    [InlineData("response.questionnaire_type", "questionnaire_type")]
    [InlineData("response.battery_type", "battery_type")]
    public async Task A_snapshot_contract_is_stored(string name, string kind)
    {
        var snapshot = Contract(name);
        var id = Guid.Parse(snapshot.GetProperty("aggregateId").GetString()!);
        _app.Catalog.Types[id] = snapshot;
        await using var scope = _app.App.Services.CreateAsyncScope();
        Assert.True(await scope.ServiceProvider.GetRequiredService<RefService>().ReadThrough(kind, id));
    }

    [Fact]
    public async Task The_page_contract_is_read_page_by_page()
    {
        var page = Contract("response.type_page");
        var handler = new StubHandler(page.GetRawText());
        var settings = Instances.Api.Config.Settings.Load(new Dictionary<string, string>
        {
            ["SETTINGS"] = "test",
            ["INSTANCES_DATABASE_URL"] = "postgres://u:p@localhost/x",
        });
        using var http = new HttpClient(handler);
        Instances.Api.Peers.HttpCatalogClient.Configure(http, settings);
        var client = new Instances.Api.Peers.HttpCatalogClient(http);
        var seen = new List<JsonElement>();
        await foreach (var snapshot in client.Snapshots("questionnaire_type"))
        {
            seen.Add(snapshot);
        }
        Assert.Single(seen);
        Assert.Equal("Bearer test-instances-to-catalog", handler.Authorization);
        Assert.EndsWith("/internal/questionnaire-types/", handler.Path);
    }

    sealed class StubHandler(string body) : HttpMessageHandler
    {
        public string? Authorization;
        public string? Path;

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Authorization = request.Headers.Authorization?.ToString();
            Path = request.RequestUri!.AbsolutePath;
            return Task.FromResult(new HttpResponseMessage(System.Net.HttpStatusCode.OK)
            {
                Content = new StringContent(body, System.Text.Encoding.UTF8, "application/json"),
            });
        }
    }
}
