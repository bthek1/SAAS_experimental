using Instances.Api.Auth;
using Instances.Api.Caching;
using Instances.Api.Data;
using Instances.Api.Http;
using Instances.Api.Refs;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Instances.Api.Api;

/// <summary>
/// Batteries: one questionnaire per slot of the battery type, in slot order. A battery is
/// created and deleted, never edited.
/// </summary>
[Route("api/batteries")]
public sealed class BatteriesController(InstancesDb db, OwnedRefs ownedRefs, RefService refs, Cache cache) : ControllerBase
{
    const string Field = "batteryTypeId";

    Guid Owner => User.OwnerId();

    /// <summary>With slots and their types, in a fixed number of queries whatever the rows.</summary>
    IQueryable<Battery> WithSlots() => db.Batteries.AsNoTracking()
        .Include(b => b.BatteryType)
        .Include(b => b.Questionnaires).ThenInclude(q => q.QuestionnaireType)
        .AsSplitQuery();

    IQueryable<Battery> Owned() => WithSlots().Where(b => b.OwnerId == Owner);

    [Authorize]
    [HttpGet("")]
    public async Task<IActionResult> List()
    {
        var pagination = Pagination.From(Request);
        var count = await db.Batteries.CountAsync(b => b.OwnerId == Owner);
        var rows = await Owned().OrderByDescending(b => b.CreatedAt).ThenByDescending(b => b.Id)
            .Skip(pagination.Skip).Take(pagination.Size).ToListAsync();
        return new ApiResult(200, pagination.Build(Request, count, rows.Select(BatteryOut.From).ToList()));
    }

    [Authorize]
    [HttpPost("")]
    public async Task<IActionResult> Create()
    {
        var body = await Body.ReadObject(Request);
        var errors = new FieldErrors();
        var typeId = await ownedRefs.Resolve(Body.Field(body, Field), Kinds.BatteryType, Field, Owner, errors, required: true);
        var name = Fields.Text(Body.Field(body, "name"), "name", errors);
        errors.ThrowIfAny();

        var batteryType = await db.BatteryTypeRefs.AsNoTracking().Include(t => t.Slots)
            .SingleAsync(t => t.Id == typeId!.Value);
        var slots = batteryType.Slots.OrderBy(s => s.Order).ToList();
        // Outside the transaction: this can call `catalog`, and each slot needs a copy.
        await refs.EnsureQuestionnaireTypes(slots.Select(s => s.QuestionnaireTypeId));

        var now = ApiJson.UtcNow();
        var battery = new Battery
        {
            Id = Guid.NewGuid(),
            OwnerId = batteryType.OwnerId,
            BatteryTypeId = batteryType.Id,
            Name = name ?? "",
            ShareToken = Guid.NewGuid(),
            CreatedAt = now,
            UpdatedAt = now,
        };
        db.Batteries.Add(battery);
        db.Questionnaires.AddRange(slots.Select(slot => new Questionnaire
        {
            Id = Guid.NewGuid(),
            OwnerId = batteryType.OwnerId,
            QuestionnaireTypeId = slot.QuestionnaireTypeId,
            BatteryId = battery.Id,
            BatteryOrder = slot.Order,
            ShareToken = Guid.NewGuid(),
            CreatedAt = now,
            UpdatedAt = now,
        }));
        // One SaveChanges is one transaction: the battery and its slots, or nothing.
        await db.SaveChangesAsync();
        return new ApiResult(201, BatteryOut.From(await WithSlots().SingleAsync(b => b.Id == battery.Id)));
    }

    [Authorize]
    [HttpGet("{id}")]
    public async Task<IActionResult> Retrieve(string id) =>
        new ApiResult(200, BatteryOut.From(
            Guid.TryParse(id, out var key) && await Owned().SingleOrDefaultAsync(b => b.Id == key) is { } found
                ? found
                : throw ApiException.NotFound()));

    [Authorize]
    [HttpDelete("{id}")]
    public async Task<IActionResult> Destroy(string id)
    {
        if (!Guid.TryParse(id, out var key) || !await db.Batteries.AnyAsync(b => b.Id == key && b.OwnerId == Owner))
        {
            throw ApiException.NotFound();
        }
        await using (var work = await UnitOfWork.Begin(db, cache))
        {
            // Its questionnaires stay, without a battery (Django's SET_NULL).
            await db.Questionnaires.Where(q => q.BatteryId == key)
                .ExecuteUpdateAsync(set => set.SetProperty(q => q.BatteryId, (Guid?)null));
            await db.Batteries.Where(b => b.Id == key).ExecuteDeleteAsync();
            work.BumpOwnerGenerationAfterCommit(Owner);
            await work.Commit();
        }
        return new ApiResult(204, null);
    }

    [AllowAnonymous]
    [HttpGet("by-token/{shareToken}")]
    public async Task<IActionResult> ReadByToken(string shareToken) =>
        new ApiResult(200, PublicBatteryOut.From(
            Guid.TryParse(shareToken, out var token)
            && await WithSlots().SingleOrDefaultAsync(b => b.ShareToken == token) is { } found
                ? found
                : throw ApiException.NotFound()));
}
