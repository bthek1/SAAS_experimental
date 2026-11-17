using System.Globalization;
using System.Text.Json;
using Instances.Api.Caching;
using Instances.Api.Data;
using Instances.Api.Http;
using Instances.Api.Peers;
using Microsoft.EntityFrameworkCore;
using Prometheus;

namespace Instances.Api.Refs;

/// <summary>A malformed event: retrying cannot help, so it is a 400, not a 5xx.</summary>
public sealed class BadEvent(string message) : Exception(message);

/// <summary>A copy of this type still has instances, so it cannot be retired.</summary>
public sealed class RefInUse : Exception;

/// <summary>
/// Local copies of `catalog`'s types, and every way they change (#13). The rules, as in
/// Django's `refs.py`:
///
/// - An event carries a type's full state and version. Applying one twice changes nothing,
///   and an older one is ignored, so duplicates and reordering are harmless.
/// - Retiring a copy deletes it and leaves a tombstone, which stops a late event from
///   bringing it back. A copy that instances use cannot be deleted.
/// - A synchronous answer from `catalog` is authoritative: the type exists right now. That
///   clears a tombstone, which is how a delete that failed after its retire heals.
/// </summary>
public sealed class RefService(InstancesDb db, Cache cache, ICatalogClient catalog, ILogger<RefService> logger)
{
    public const string Applied = "applied";
    public const string Ignored = "ignored";

    static readonly Counter ReadThroughs = Metrics.CreateCounter(
        "app_ref_read_through_total",
        "Copies fetched from catalog because they had not arrived, by result.",
        "result");

    /// <summary>Apply one event from `catalog`. Safe to call any number of times.</summary>
    public async Task<string> ApplyEvent(JsonElement body)
    {
        var parsed = ParsedEvent.From(body);
        await using var work = await UnitOfWork.Begin(db, cache);
        var result = await Apply(parsed, work);
        await work.Commit();
        return result;
    }

    async Task<string> Apply(ParsedEvent e, UnitOfWork work)
    {
        if (e.Kind == "user" && e.Action is "deactivated" or "reactivated" or "deleted")
        {
            return await ApplyUserEvent(e.Action, e.AggregateId(), e.Version(), work);
        }
        if (!Kinds.IsKnown(e.Kind) || e.Action is not ("changed" or "deleted"))
        {
            throw new BadEvent($"unknown event type '{e.Type}'");
        }
        var refId = e.AggregateId();
        if (await db.RetiredRefs.AnyAsync(r => r.Kind == e.Kind && r.RefId == refId))
        {
            return Ignored;
        }
        if (e.Action == "deleted")
        {
            return await ApplyDeleted(e.Kind, refId, e.Version(), work);
        }
        var data = TypeData.From(e.Kind, e.Data());
        // An owner's type event can arrive after the event that deleted the owner.
        if (await db.BlockedOwners.AnyAsync(b => b.OwnerId == data.OwnerId && b.Deleted))
        {
            return Ignored;
        }
        return await Upsert(e.Kind, refId, e.Version(), data, work);
    }

    /// <summary>Store an authoritative answer from `catalog`, clearing any tombstone.</summary>
    public async Task StoreSnapshot(JsonElement snapshot)
    {
        var parsed = ParsedEvent.From(snapshot);
        var kind = parsed.Kind;
        if (!Kinds.IsKnown(kind))
        {
            throw new BadEvent($"unknown snapshot type '{parsed.Type}'");
        }
        var refId = parsed.AggregateId();
        var data = TypeData.From(kind, parsed.Data());
        await using var work = await UnitOfWork.Begin(db, cache);
        await db.RetiredRefs.Where(r => r.Kind == kind && r.RefId == refId).ExecuteDeleteAsync();
        await Upsert(kind, refId, parsed.Version(), data, work);
        await work.Commit();
    }

    async Task<string> Upsert(string kind, Guid refId, long version, TypeData data, UnitOfWork work)
    {
        // Insert, or lock the row that is there: two events for one type serialize here.
        var created = kind == Kinds.QuestionnaireType
            ? await db.Database.ExecuteSqlInterpolatedAsync($"""
                INSERT INTO questionnaires_questionnairetyperef
                    (id, title, created_at, updated_at, version, owner_id, questionnaire_json)
                VALUES ({refId}, {data.Title}, {data.CreatedAt}, {data.UpdatedAt}, {version}, {data.OwnerId},
                        CAST({data.QuestionnaireJson} AS jsonb))
                ON CONFLICT (id) DO NOTHING
                """) == 1
            : await db.Database.ExecuteSqlInterpolatedAsync($"""
                INSERT INTO questionnaires_batterytyperef
                    (id, title, created_at, updated_at, version, owner_id, description)
                VALUES ({refId}, {data.Title}, {data.CreatedAt}, {data.UpdatedAt}, {version}, {data.OwnerId},
                        {data.Description})
                ON CONFLICT (id) DO NOTHING
                """) == 1;

        if (!created)
        {
            var current = kind == Kinds.QuestionnaireType
                ? await db.Database.SqlQuery<long>(
                    $"SELECT version AS \"Value\" FROM questionnaires_questionnairetyperef WHERE id = {refId} FOR UPDATE")
                    .SingleAsync()
                : await db.Database.SqlQuery<long>(
                    $"SELECT version AS \"Value\" FROM questionnaires_batterytyperef WHERE id = {refId} FOR UPDATE")
                    .SingleAsync();
            if (current >= version)
            {
                return Ignored;
            }
            if (kind == Kinds.QuestionnaireType)
            {
                await db.Database.ExecuteSqlInterpolatedAsync($"""
                    UPDATE questionnaires_questionnairetyperef
                    SET title = {data.Title}, created_at = {data.CreatedAt}, updated_at = {data.UpdatedAt},
                        version = {version}, owner_id = {data.OwnerId},
                        questionnaire_json = CAST({data.QuestionnaireJson} AS jsonb)
                    WHERE id = {refId}
                    """);
            }
            else
            {
                await db.Database.ExecuteSqlInterpolatedAsync($"""
                    UPDATE questionnaires_batterytyperef
                    SET title = {data.Title}, created_at = {data.CreatedAt}, updated_at = {data.UpdatedAt},
                        version = {version}, owner_id = {data.OwnerId}, description = {data.Description}
                    WHERE id = {refId}
                    """);
            }
        }
        if (kind == Kinds.BatteryType)
        {
            await db.BatteryTypeRefSlots.Where(s => s.BatteryTypeId == refId).ExecuteDeleteAsync();
            db.BatteryTypeRefSlots.AddRange(data.Items.Select(item => new BatteryTypeRefSlot
            {
                BatteryTypeId = refId,
                QuestionnaireTypeId = item.QuestionnaireTypeId,
                Order = item.Order,
            }));
            await db.SaveChangesAsync();
        }
        // Dashboards show titles, and score labels come from the definition.
        work.BumpOwnerGenerationAfterCommit(data.OwnerId);
        return Applied;
    }

    async Task<string> ApplyDeleted(string kind, Guid refId, long version, UnitOfWork work)
    {
        var existing = await Current(kind, refId);
        if (existing is { } copy)
        {
            if (copy.Version >= version)
            {
                return Ignored;
            }
            if (await InUse(kind, refId))
            {
                // An instance was created between the retire and the delete, through a
                // read-through. Its answers stay readable; reconcile-refs reports it.
                logger.LogWarning("deleted {Kind} {RefId} still has instances", kind, refId);
                return Ignored;
            }
            await Delete(kind, refId);
            work.BumpOwnerGenerationAfterCommit(copy.OwnerId);
        }
        await Tombstone(kind, refId);
        return Applied;
    }

    async Task<string> ApplyUserEvent(string action, Guid ownerId, long version, UnitOfWork work)
    {
        var row = await db.BlockedOwners
            .FromSqlInterpolated($"SELECT * FROM questionnaires_blockedowner WHERE owner_id = {ownerId} FOR UPDATE")
            .AsNoTracking()
            .SingleOrDefaultAsync();
        if (row is not null && (row.Deleted || row.Version >= version))
        {
            return Ignored;
        }
        var blocked = action != "reactivated";
        var deleted = action == "deleted";
        await db.Database.ExecuteSqlInterpolatedAsync($"""
            INSERT INTO questionnaires_blockedowner (owner_id, blocked, deleted, version)
            VALUES ({ownerId}, {blocked}, {deleted}, {version})
            ON CONFLICT (owner_id) DO UPDATE
            SET blocked = EXCLUDED.blocked, deleted = EXCLUDED.deleted, version = EXCLUDED.version
            """);
        if (deleted)
        {
            // In this order: the copies are RESTRICTed by what is made from them.
            await db.Questionnaires.Where(q => q.OwnerId == ownerId).ExecuteDeleteAsync();
            await db.Batteries.Where(b => b.OwnerId == ownerId).ExecuteDeleteAsync();
            await db.QuestionnaireTypeRefs.Where(t => t.OwnerId == ownerId).ExecuteDeleteAsync();
            await db.BatteryTypeRefSlots
                .Where(s => db.BatteryTypeRefs.Any(t => t.Id == s.BatteryTypeId && t.OwnerId == ownerId))
                .ExecuteDeleteAsync();
            await db.BatteryTypeRefs.Where(t => t.OwnerId == ownerId).ExecuteDeleteAsync();
        }
        work.BumpOwnerGenerationAfterCommit(ownerId);
        return Applied;
    }

    /// <summary>Delete a copy before its source goes. Throws <see cref="RefInUse"/> if instances use it.</summary>
    public async Task Retire(string kind, Guid refId)
    {
        await using var work = await UnitOfWork.Begin(db, cache);
        var existing = await Current(kind, refId, forUpdate: true);
        if (existing is { } copy)
        {
            if (await InUse(kind, refId))
            {
                throw new RefInUse();
            }
            await Delete(kind, refId);
            work.BumpOwnerGenerationAfterCommit(copy.OwnerId);
        }
        await Tombstone(kind, refId);
        await work.Commit();
    }

    /// <summary>The copy, fetched from `catalog`. False if `catalog` has no such type.</summary>
    public async Task<bool> ReadThrough(string kind, Guid refId)
    {
        JsonElement? snapshot;
        try
        {
            snapshot = await catalog.Fetch(kind, refId);
        }
        catch (PeerUnavailable)
        {
            ReadThroughs.WithLabels("unavailable").Inc();
            throw;
        }
        ReadThroughs.WithLabels(snapshot is null ? "missing" : "found").Inc();
        if (snapshot is not { } found)
        {
            return false;
        }
        try
        {
            await StoreSnapshot(found);
        }
        catch (BadEvent exc)
        {
            throw new PeerUnavailable($"catalog sent an unusable snapshot: {exc.Message}", exc);
        }
        return true;
    }

    /// <summary>As <see cref="ReadThrough"/>, with `catalog` unreachable as a 503.</summary>
    public async Task<bool> ReadThroughOr503(string kind, Guid refId)
    {
        try
        {
            return await ReadThrough(kind, refId);
        }
        catch (PeerUnavailable)
        {
            throw ApiException.Detail(503, Messages.Unavailable);
        }
    }

    /// <summary>Fetch any of these copies that have not arrived yet.</summary>
    public async Task EnsureQuestionnaireTypes(IEnumerable<Guid> ids)
    {
        var wanted = ids.ToHashSet();
        var present = await db.QuestionnaireTypeRefs.Where(t => wanted.Contains(t.Id)).Select(t => t.Id).ToListAsync();
        foreach (var refId in wanted.Except(present))
        {
            if (!await ReadThroughOr503(Kinds.QuestionnaireType, refId))
            {
                // The slot list is out of date. The battery type's own event will fix it.
                throw ApiException.Detail(503, Messages.Unavailable);
            }
        }
    }

    readonly record struct Copy(Guid OwnerId, long Version);

    async Task<Copy?> Current(string kind, Guid refId, bool forUpdate = false)
    {
        FormattableString sql = (kind == Kinds.QuestionnaireType, forUpdate) switch
        {
            (true, false) => $"SELECT owner_id AS \"OwnerId\", version AS \"Version\" FROM questionnaires_questionnairetyperef WHERE id = {refId}",
            (true, true) => $"SELECT owner_id AS \"OwnerId\", version AS \"Version\" FROM questionnaires_questionnairetyperef WHERE id = {refId} FOR UPDATE",
            (false, false) => $"SELECT owner_id AS \"OwnerId\", version AS \"Version\" FROM questionnaires_batterytyperef WHERE id = {refId}",
            (false, true) => $"SELECT owner_id AS \"OwnerId\", version AS \"Version\" FROM questionnaires_batterytyperef WHERE id = {refId} FOR UPDATE",
        };
        var rows = await db.Database.SqlQuery<CopyRow>(sql).ToListAsync();
        return rows.Count == 0 ? null : new Copy(rows[0].OwnerId, rows[0].Version);
    }

    sealed class CopyRow
    {
        public Guid OwnerId { get; set; }
        public long Version { get; set; }
    }

    Task<bool> InUse(string kind, Guid refId) => kind == Kinds.QuestionnaireType
        ? db.Questionnaires.AnyAsync(q => q.QuestionnaireTypeId == refId)
        : db.Batteries.AnyAsync(b => b.BatteryTypeId == refId);

    async Task Delete(string kind, Guid refId)
    {
        if (kind == Kinds.QuestionnaireType)
        {
            await db.QuestionnaireTypeRefs.Where(t => t.Id == refId).ExecuteDeleteAsync();
            return;
        }
        await db.BatteryTypeRefSlots.Where(s => s.BatteryTypeId == refId).ExecuteDeleteAsync();
        await db.BatteryTypeRefs.Where(t => t.Id == refId).ExecuteDeleteAsync();
    }

    Task Tombstone(string kind, Guid refId) => db.Database.ExecuteSqlInterpolatedAsync($"""
        INSERT INTO questionnaires_retiredref (kind, ref_id, retired_at)
        VALUES ({kind}, {refId}, {ApiJson.UtcNow()})
        ON CONFLICT (kind, ref_id) DO NOTHING
        """);
}

/// <summary>An event's envelope. Anything missing or of the wrong type is a <see cref="BadEvent"/>.</summary>
sealed class ParsedEvent
{
    readonly JsonElement _body;

    public string Type { get; }
    public string Kind { get; }
    public string Action { get; }

    ParsedEvent(JsonElement body, string type)
    {
        _body = body;
        Type = type;
        var dot = type.LastIndexOf('.');
        Kind = dot < 0 ? "" : type[..dot];
        Action = dot < 0 ? type : type[(dot + 1)..];
    }

    public static ParsedEvent From(JsonElement body)
    {
        if (body.ValueKind != JsonValueKind.Object)
        {
            throw new BadEvent("an event is a JSON object");
        }
        var type = Field(body, "type");
        return type.ValueKind == JsonValueKind.String
            ? new ParsedEvent(body, type.GetString()!)
            : throw new BadEvent("'type' is not a string");
    }

    public Guid AggregateId() => Uuid(Field(_body, "aggregateId"), "aggregateId");

    public long Version()
    {
        var version = Field(_body, "version");
        return version.ValueKind == JsonValueKind.Number && version.TryGetInt64(out var value) && value >= 0
            ? value
            : throw new BadEvent("'version' is not a whole number");
    }

    public JsonElement Data()
    {
        var data = Field(_body, "data");
        return data.ValueKind == JsonValueKind.Object ? data : throw new BadEvent("'data' is not an object");
    }

    internal static JsonElement Field(JsonElement element, string name) =>
        element.ValueKind == JsonValueKind.Object && element.TryGetProperty(name, out var value)
            ? value
            : throw new BadEvent($"'{name}'");

    internal static Guid Uuid(JsonElement element, string name) =>
        element.ValueKind == JsonValueKind.String && Guid.TryParse(element.GetString(), out var id)
            ? id
            : throw new BadEvent($"'{name}' is not a UUID");
}

sealed record SlotItem(Guid QuestionnaireTypeId, int Order);

/// <summary>A type's full state, from an event's or a snapshot's `data`.</summary>
sealed record TypeData(
    Guid OwnerId,
    string Title,
    DateTime CreatedAt,
    DateTime UpdatedAt,
    string QuestionnaireJson,
    string Description,
    IReadOnlyList<SlotItem> Items)
{
    public static TypeData From(string kind, JsonElement data)
    {
        var ownerId = ParsedEvent.Uuid(ParsedEvent.Field(data, "ownerId"), "ownerId");
        var title = Text(data, "title");
        var createdAt = Time(data, "createdAt");
        var updatedAt = Time(data, "updatedAt");
        if (kind == Kinds.QuestionnaireType)
        {
            var json = ParsedEvent.Field(data, "questionnaireJson").GetRawText();
            return new TypeData(ownerId, title, createdAt, updatedAt, json, "", []);
        }
        var items = ParsedEvent.Field(data, "items");
        if (items.ValueKind != JsonValueKind.Array)
        {
            throw new BadEvent("'items' is not a list");
        }
        var slots = items.EnumerateArray().Select(item =>
        {
            var order = ParsedEvent.Field(item, "order");
            return new SlotItem(
                ParsedEvent.Uuid(ParsedEvent.Field(item, "questionnaireTypeId"), "questionnaireTypeId"),
                order.ValueKind == JsonValueKind.Number && order.TryGetInt32(out var value) && value >= 0
                    ? value
                    : throw new BadEvent("'order' is not a whole number"));
        }).ToList();
        return new TypeData(ownerId, title, createdAt, updatedAt, "{}", Text(data, "description"), slots);
    }

    static string Text(JsonElement data, string name)
    {
        var value = ParsedEvent.Field(data, name);
        return value.ValueKind == JsonValueKind.String ? value.GetString()! : throw new BadEvent($"'{name}' is not text");
    }

    static DateTime Time(JsonElement data, string name)
    {
        var text = Text(data, name);
        return DateTimeOffset.TryParse(text, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var value)
            ? value.UtcDateTime
            : throw new BadEvent($"'{name}' is not a timestamp");
    }
}
