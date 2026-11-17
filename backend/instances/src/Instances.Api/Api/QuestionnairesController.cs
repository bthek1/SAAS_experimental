using Instances.Api.Auth;
using Instances.Api.Caching;
using Instances.Api.Data;
using System.Text.RegularExpressions;
using Instances.Api.Http;
using Instances.Api.Pdf;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Instances.Api.Api;

/// <summary>
/// The owner's questionnaires, and the share-link endpoints a respondent uses. Every owner
/// query is scoped to the token's owner; another owner's row is a 404.
/// </summary>
[Route("api/questionnaires")]
public sealed class QuestionnairesController(InstancesDb db, OwnedRefs ownedRefs, Cache cache) : ControllerBase
{
    const string Field = "questionnaireTypeId";

    Guid Owner => User.OwnerId();

    IQueryable<Questionnaire> Owned() => db.Questionnaires.AsNoTracking()
        .Include(q => q.QuestionnaireType)
        .Where(q => q.OwnerId == Owner);

    [Authorize]
    [HttpGet("")]
    public async Task<IActionResult> List()
    {
        var errors = new FieldErrors();
        var query = Owned();
        if (Query.Get(Request, "questionnaireType") is { } typeText)
        {
            if (await ownedRefs.Resolve(typeText, Kinds.QuestionnaireType, "questionnaireType", Owner, errors) is { } typeId)
            {
                query = query.Where(q => q.QuestionnaireTypeId == typeId);
            }
        }
        var submitted = Fields.Boolean(Query.Get(Request, "submitted"), "submitted", errors);
        errors.ThrowIfAny();
        if (submitted is { } wanted)
        {
            query = wanted ? query.Where(q => q.SubmittedAt != null) : query.Where(q => q.SubmittedAt == null);
        }

        var pagination = Pagination.From(Request);
        var count = await query.CountAsync();
        // Newest first, then id: rows made in one request share a created_at, and a tie
        // would let a row repeat or vanish between pages.
        var rows = await query.OrderByDescending(q => q.CreatedAt).ThenByDescending(q => q.Id)
            .Skip(pagination.Skip).Take(pagination.Size).ToListAsync();
        return new ApiResult(200, pagination.Build(Request, count, rows.Select(QuestionnaireOut.From).ToList()));
    }

    [Authorize]
    [HttpPost("")]
    public async Task<IActionResult> Create()
    {
        var body = await Body.ReadObject(Request);
        var errors = new FieldErrors();
        var typeId = await ownedRefs.Resolve(Body.Field(body, Field), Kinds.QuestionnaireType, Field, Owner, errors, required: true);
        var name = Fields.Text(Body.Field(body, "name"), "name", errors);
        errors.ThrowIfAny();

        var now = ApiJson.UtcNow();
        var questionnaire = new Questionnaire
        {
            Id = Guid.NewGuid(),
            OwnerId = Owner,
            QuestionnaireTypeId = typeId!.Value,
            Name = name ?? "",
            ShareToken = Guid.NewGuid(),
            CreatedAt = now,
            UpdatedAt = now,
        };
        db.Questionnaires.Add(questionnaire);
        await db.SaveChangesAsync();
        return new ApiResult(201, QuestionnaireOut.From(await Owned().SingleAsync(q => q.Id == questionnaire.Id)));
    }

    [Authorize]
    [HttpGet("{id}")]
    public async Task<IActionResult> Retrieve(string id) =>
        new ApiResult(200, QuestionnaireOut.From(await Find(id)));

    [Authorize]
    [HttpPatch("{id}")]
    public async Task<IActionResult> Update(string id)
    {
        var questionnaire = await Find(id);
        var body = await Body.ReadObject(Request);
        var errors = new FieldErrors();
        var typeField = Body.Field(body, Field);
        var typeId = await ownedRefs.Resolve(typeField, Kinds.QuestionnaireType, Field, Owner, errors, required: false);
        if (typeId is { } changed && changed != questionnaire.QuestionnaireTypeId)
        {
            errors.Add(Field, "The type of an existing questionnaire cannot change.");
        }
        var name = Fields.Text(Body.Field(body, "name"), "name", errors);
        errors.ThrowIfAny();

        await db.Questionnaires.Where(q => q.Id == questionnaire.Id).ExecuteUpdateAsync(set => set
            .SetProperty(q => q.Name, q => name ?? q.Name)
            .SetProperty(q => q.UpdatedAt, ApiJson.UtcNow()));
        return new ApiResult(200, QuestionnaireOut.From(await Owned().SingleAsync(q => q.Id == questionnaire.Id)));
    }

    [Authorize]
    [HttpDelete("{id}")]
    public async Task<IActionResult> Destroy(string id)
    {
        var questionnaire = await Find(id);
        await db.Questionnaires.Where(q => q.Id == questionnaire.Id).ExecuteDeleteAsync();
        // So a dashboard never links to a deleted row.
        await cache.BumpOwnerGeneration(Owner);
        return new ApiResult(204, null);
    }

    static readonly TimeSpan PdfCacheFor = TimeSpan.FromHours(24);
    const int PdfCacheMaxBytes = 2 * 1024 * 1024;
    // Bump when Pdf/ResponsePdf.cs changes what it draws.
    const int PdfCacheVersion = 1;

    [Authorize]
    [HttpGet("{id}/pdf")]
    public async Task<IActionResult> Pdf(string id)
    {
        var questionnaire = await Find(id);
        if (questionnaire.SubmittedAt is null)
        {
            throw ApiException.Detail(400, "This questionnaire has not been submitted.");
        }
        var safe = Regex.Replace(questionnaire.QuestionnaireType.Title, "[^A-Za-z0-9_-]+", "-").Trim('-');
        var stem = safe.Length > 60 ? safe[..60] : safe;
        var filename = $"{(stem.Length > 0 ? stem : "response")}-{DateTime.UtcNow:yyyy-MM-dd}.pdf";
        // A submitted response never changes. The PDF also reads its name and the type's
        // title, so these timestamps identify the content: no generation needed.
        var pdf = await cache.Cached(
            "pdf",
            Owner,
            new
            {
                id = questionnaire.Id,
                updatedAt = ApiJson.Format(questionnaire.UpdatedAt),
                typeUpdatedAt = ApiJson.Format(questionnaire.QuestionnaireType.UpdatedAt),
            },
            PdfCacheFor,
            () => Task.Run(() => ResponsePdf.Render(questionnaire)),
            version: PdfCacheVersion,
            useGeneration: false,
            storeIf: content => content.Length <= PdfCacheMaxBytes);
        Response.Headers.ContentDisposition = $"attachment; filename=\"{filename}\"";
        return File(pdf, "application/pdf");
    }

    async Task<Questionnaire> Find(string id) =>
        Guid.TryParse(id, out var key) && await Owned().SingleOrDefaultAsync(q => q.Id == key) is { } found
            ? found
            : throw ApiException.NotFound();

    // ── Share links: no authentication at all, so a stale token cannot 401 ──────

    IQueryable<Questionnaire> ByToken(string shareToken) =>
        Guid.TryParse(shareToken, out var token)
            ? db.Questionnaires.AsNoTracking().Include(q => q.QuestionnaireType).Where(q => q.ShareToken == token)
            : throw ApiException.NotFound();

    [AllowAnonymous]
    [HttpGet("by-token/{shareToken}")]
    public async Task<IActionResult> ReadByToken(string shareToken) =>
        new ApiResult(200, PublicQuestionnaireOut.From(
            await ByToken(shareToken).SingleOrDefaultAsync() ?? throw ApiException.NotFound()));

    [AllowAnonymous]
    [HttpPatch("by-token/{shareToken}/submit")]
    public async Task<IActionResult> Submit(string shareToken)
    {
        var questionnaire = await ByToken(shareToken).SingleOrDefaultAsync() ?? throw ApiException.NotFound();
        var body = await Body.ReadObject(Request);
        var errors = new FieldErrors();
        var answers = Fields.Object(Body.Field(body, "answers"), "answers", errors, required: true);
        var metrics = Fields.Object(Body.Field(body, "metrics"), "metrics", errors, required: false) ?? RawJson.EmptyObject;
        errors.ThrowIfAny();

        // Once only, with the type's current definition as the snapshot, in one statement:
        // whichever of two submits commits first wins, and the other finds it submitted.
        var now = ApiJson.UtcNow();
        var updated = await db.Database.ExecuteSqlInterpolatedAsync($"""
            UPDATE questionnaires_questionnaire AS q
            SET answers_json = CAST({answers!.Value.Text} AS jsonb),
                metrics_json = CAST({metrics.Text} AS jsonb),
                questionnaire_json_snapshot = t.questionnaire_json,
                submitted_at = {now},
                updated_at = {now}
            FROM questionnaires_questionnairetyperef AS t
            WHERE q.id = {questionnaire.Id} AND t.id = q.questionnaire_type_id AND q.submitted_at IS NULL
            """);
        if (updated == 0)
        {
            throw ApiException.Detail(409, "Already submitted.");
        }
        var submitted = await db.Questionnaires.AsNoTracking().Include(q => q.QuestionnaireType)
            .SingleAsync(q => q.Id == questionnaire.Id);
        return new ApiResult(200, PublicQuestionnaireOut.From(submitted));
    }
}
