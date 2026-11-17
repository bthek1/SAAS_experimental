using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Instances.Api.Commands;
using Instances.Api.Data;
using Instances.Api.Pdf;
using Instances.Api.Refs;
using Instances.Tests.Support;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Instances.Tests;

/// <summary>Django's `test_pdf.py` cases for resolving a response, ported (#43).</summary>
[Trait("Category", "Pdf")]
public sealed class PdfContentTests
{
    internal const string Survey = """
        {
          "pages": [{"name": "p1", "elements": [
            {"type": "text", "name": "q1", "title": "Your name"},
            {"type": "radiogroup", "name": "color", "title": "Colour", "choices": [{"value": "r", "text": "Red"}, "blue"]},
            {"type": "checkbox", "name": "pets", "choices": ["cat", "dog"]},
            {"type": "boolean", "name": "ok", "title": "OK?"},
            {"type": "panel", "name": "panel1", "elements": [{"type": "comment", "name": "note", "title": "Note"}]},
            {"type": "matrix", "name": "grid", "title": "Grid",
             "columns": [{"value": 1, "text": "Low"}, {"value": 2, "text": "High"}],
             "rows": [{"value": "a", "text": "Row A"}, "b"]},
            {"type": "html", "name": "intro", "html": "<p>hi</p>"}
          ]}],
          "calculatedValues": [
            {"name": "total_score", "expression": "1"},
            {"name": "risk", "title": "Risk level", "expression": "2"}
          ]
        }
        """;

    internal const string Answers = """
        {"q1": "Pat", "color": "r", "pets": ["cat", "dog"], "ok": true, "note": "Fine", "grid": {"a": 2}}
        """;

    static JsonElement Json(string text) => JsonDocument.Parse(text).RootElement.Clone();

    [Fact]
    public void Labels_flattening_and_skips()
    {
        var questions = ResponseContent.Questions(Json(Survey), Json(Answers));
        Assert.Equal(["Your name", "Colour", "pets", "OK?", "Note", "Grid"], questions.Select(q => q.Title));
        var answers = questions.OfType<AnswerQuestion>().ToDictionary(q => q.Title, q => q.DisplayValue);
        Assert.Equal("Red", answers["Colour"]);
        Assert.Equal("cat, dog", answers["pets"]);
        Assert.Equal("Yes", answers["OK?"]);
        Assert.Equal("Fine", answers["Note"]);
        var grid = Assert.Single(questions.OfType<MatrixQuestion>());
        Assert.Equal(["Low", "High"], grid.Columns);
        Assert.Equal([new MatrixRow("Row A", "High"), new MatrixRow("b", null)], grid.Rows);
    }

    [Fact]
    public void Missing_answers_are_empty() =>
        Assert.Equal("", ((AnswerQuestion)ResponseContent.Questions(Json(Survey), Json("{}"))[0]).DisplayValue);

    [Fact]
    public void Malformed_definitions_are_tolerated() =>
        Assert.Empty(ResponseContent.Questions(Json("""{"pages": [null, {"elements": [null, "x"]}]}"""), Json("{}")));

    [Fact]
    public void Metrics_use_titles_and_the_definitions_order() =>
        Assert.Equal(
            [new ResolvedMetric("Total Score", "7"), new ResolvedMetric("Risk level", "low")],
            ResponseContent.Metrics(Json(Survey), Json("""{"risk": "low", "total_score": 7, "other": 1}""")));

    [Theory]
    [InlineData("7", "7")]
    [InlineData("2.0", "2.0")]
    [InlineData("1.50", "1.5")]
    [InlineData("true", "True")]
    [InlineData("null", "None")]
    [InlineData("\"x\"", "x")]
    public void Values_print_as_python_prints_them(string json, string expected) =>
        Assert.Equal(expected, ResponseContent.PyStr(Json(json)));

    [Theory]
    [InlineData("total score", "Total Score")]
    [InlineData("abc1def", "Abc1Def")]
    [InlineData("PHQ score", "Phq Score")]
    public void Titles_case_as_python_does(string text, string expected) =>
        Assert.Equal(expected, ResponseContent.PythonTitle(text));
}

/// <summary>The download itself: headers, owner scoping and the cache's rules for PDFs.</summary>
[Trait("Category", "Pdf")]
public sealed class PdfEndpointTests(Postgres postgres) : IAsyncLifetime
{
    TestApp _app = null!;

    public async ValueTask InitializeAsync() => _app = await TestApp.Start(postgres, cacheEnabled: true);

    public async ValueTask DisposeAsync() => await _app.DisposeAsync();

    async Task<(HttpClient Owner, string Id, Guid TypeId, Guid OwnerId)> Submitted()
    {
        var ownerId = Guid.NewGuid();
        var typeId = Guid.NewGuid();
        await _app.Send(Events.QuestionnaireType(ownerId, typeId, title: "Check in / weekly",
            json: JsonSerializer.Deserialize<JsonElement>(PdfContentTests.Survey)));
        var owner = _app.Owner(ownerId);
        var created = await Seed.Json(await owner.PostAsJsonAsync("/api/questionnaires/", new { questionnaireTypeId = typeId, name = "Pat" }));
        var submit = await _app.Client.PatchAsJsonAsync(
            $"/api/questionnaires/by-token/{created.GetProperty("shareToken").GetString()}/submit/",
            new { answers = JsonSerializer.Deserialize<JsonElement>(PdfContentTests.Answers), metrics = new { total_score = 7, risk = "low" } });
        Assert.Equal(HttpStatusCode.OK, submit.StatusCode);
        return (owner, created.GetProperty("id").GetString()!, typeId, ownerId);
    }

    [Fact]
    public async Task A_download()
    {
        var (owner, id, _, _) = await Submitted();
        var response = await owner.GetAsync($"/api/questionnaires/{id}/pdf/");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("application/pdf", response.Content.Headers.ContentType!.MediaType);
        Assert.Equal($"attachment; filename=\"Check-in-weekly-{DateTime.UtcNow:yyyy-MM-dd}.pdf\"",
            response.Content.Headers.GetValues("Content-Disposition").Single());
        Assert.StartsWith("%PDF", System.Text.Encoding.ASCII.GetString(await response.Content.ReadAsByteArrayAsync())[..4]);
    }

    [Fact]
    public async Task A_second_download_is_the_cached_bytes_and_a_rename_renders_again()
    {
        var (owner, id, _, _) = await Submitted();
        var first = await (await owner.GetAsync($"/api/questionnaires/{id}/pdf/")).Content.ReadAsByteArrayAsync();
        Assert.Single(_app.Store.Keys, key => key.StartsWith("pdf:"));
        var second = await (await owner.GetAsync($"/api/questionnaires/{id}/pdf/")).Content.ReadAsByteArrayAsync();
        Assert.Equal(first, second);
        await owner.PatchAsJsonAsync($"/api/questionnaires/{id}/", new { name = "Sam" });
        await owner.GetAsync($"/api/questionnaires/{id}/pdf/");
        Assert.Equal(2, _app.Store.Keys.Count(key => key.StartsWith("pdf:")));
    }

    [Fact]
    public async Task Another_owner_gets_404_even_with_a_cached_pdf()
    {
        var (owner, id, _, _) = await Submitted();
        Assert.Equal(HttpStatusCode.OK, (await owner.GetAsync($"/api/questionnaires/{id}/pdf/")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await _app.Owner(Guid.NewGuid()).GetAsync($"/api/questionnaires/{id}/pdf/")).StatusCode);
    }

    [Fact]
    public async Task A_generation_bump_keeps_the_pdf()
    {
        var (owner, id, _, ownerId) = await Submitted();
        await owner.GetAsync($"/api/questionnaires/{id}/pdf/");
        await _app.Service<Instances.Api.Caching.Cache>().BumpOwnerGeneration(ownerId);
        await owner.GetAsync($"/api/questionnaires/{id}/pdf/");
        Assert.Single(_app.Store.Keys, key => key.StartsWith("pdf:"));
    }
}

/// <summary>The verbs of the service binary (#43).</summary>
[Trait("Category", "Commands")]
public sealed class CommandTests(Postgres postgres) : IAsyncLifetime
{
    TestApp _app = null!;

    public async ValueTask InitializeAsync() => _app = await TestApp.Start(postgres);

    public async ValueTask DisposeAsync() => await _app.DisposeAsync();

    /// <summary>What `catalog`'s seeder sends for one load-test owner.</summary>
    async Task<Guid> LoadTestOwner()
    {
        var ownerId = Guid.NewGuid();
        var scales = new List<Guid>();
        foreach (var n in new[] { 1, 2, 3 })
        {
            var id = Guid.NewGuid();
            await _app.Send(Events.QuestionnaireType(ownerId, id, title: $"Scale {n}"));
            scales.Add(id);
        }
        await _app.Send(Events.BatteryType(ownerId, Guid.NewGuid(), scales.Take(2), title: "Intake battery"));
        return ownerId;
    }

    [Fact]
    public async Task Seed_spreads_rows_over_ninety_days_and_never_seeds_an_owner_twice()
    {
        var owners = new[] { await LoadTestOwner(), await LoadTestOwner() };
        var now = DateTime.UtcNow;
        await using var db = _app.Db();
        var result = await new Seeding(db).Seed(questionnairesPerOwner: 200, seed: 1234, now: now);
        Assert.Equal((2, 0, 2 * 20, 2 * 200), (result.OwnersSeeded, result.OwnersSkipped, result.Batteries, result.Questionnaires));
        foreach (var ownerId in owners)
        {
            var rows = await db.Questionnaires.Where(q => q.OwnerId == ownerId).ToListAsync();
            Assert.Equal(200, rows.Count);
            Assert.Equal(40, rows.Count(q => q.BatteryId != null));
            var submitted = rows.Count(q => q.SubmittedAt != null);
            Assert.InRange(submitted, 110, 170);
            Assert.All(rows, q => Assert.InRange(q.CreatedAt, now.AddDays(-90).AddSeconds(-1), now));
            Assert.All(rows.Where(q => q.SubmittedAt != null), q =>
            {
                Assert.InRange(q.SubmittedAt!.Value, q.CreatedAt, now);
                Assert.Contains("\"total\"", q.MetricsJson);
            });
        }
        var again = await new Seeding(db).Seed(200, 1234);
        Assert.Equal((0, 2), (again.OwnersSeeded, again.OwnersSkipped));
    }

    [Fact]
    public async Task Reconcile_repairs_a_missing_and_a_stale_copy_and_retires_a_gone_one()
    {
        var ownerId = Guid.NewGuid();
        Guid stale = Guid.NewGuid(), missing = Guid.NewGuid(), gone = Guid.NewGuid(), current = Guid.NewGuid();
        await _app.Send(Events.QuestionnaireType(ownerId, stale, 1, "Old"));
        await _app.Send(Events.QuestionnaireType(ownerId, gone, 1, "Gone"));
        await _app.Send(Events.QuestionnaireType(ownerId, current, 4, "Same"));
        _app.Catalog.Types[stale] = Events.Json(Events.QuestionnaireType(ownerId, stale, 2, "New"));
        _app.Catalog.Types[missing] = Events.Json(Events.QuestionnaireType(ownerId, missing, 1, "Missing"));
        _app.Catalog.Types[current] = Events.Json(Events.QuestionnaireType(ownerId, current, 4, "Same"));

        async Task<ReconcileReport> Run(bool dryRun)
        {
            await using var scope = _app.App.Services.CreateAsyncScope();
            var provider = scope.ServiceProvider;
            return await new Reconcile(provider.GetRequiredService<InstancesDb>(), provider.GetRequiredService<RefService>(),
                provider.GetRequiredService<Instances.Api.Peers.ICatalogClient>()).Run(dryRun);
        }

        var dry = await Run(dryRun: true);
        Assert.Equal(3, dry.Differences);
        await using (var db = _app.Db())
        {
            Assert.Equal("Old", (await db.QuestionnaireTypeRefs.SingleAsync(t => t.Id == stale)).Title);
        }

        var report = await Run(dryRun: false);
        Assert.Equal([$"questionnaire_type {missing}"], report.Created);
        Assert.Equal([$"questionnaire_type {stale}"], report.Updated);
        Assert.Equal([$"questionnaire_type {gone}"], report.Removed);
        await using var check = _app.Db();
        Assert.Equal("New", (await check.QuestionnaireTypeRefs.SingleAsync(t => t.Id == stale)).Title);
        Assert.True(await check.QuestionnaireTypeRefs.AnyAsync(t => t.Id == missing));
        Assert.False(await check.QuestionnaireTypeRefs.AnyAsync(t => t.Id == gone));
        Assert.Equal(0, (await Run(dryRun: false)).Differences);
    }
}
