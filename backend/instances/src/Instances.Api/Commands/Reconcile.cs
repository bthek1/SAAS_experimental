using Instances.Api.Data;
using Instances.Api.Peers;
using Instances.Api.Refs;
using Microsoft.EntityFrameworkCore;

namespace Instances.Api.Commands;

public sealed class ReconcileReport
{
    public List<string> Created { get; } = [];
    public List<string> Updated { get; } = [];
    public List<string> Removed { get; } = [];
    public List<string> OrphansInUse { get; } = [];

    public int Differences => Created.Count + Updated.Count + Removed.Count + OrphansInUse.Count;

    public IEnumerable<(string Name, List<string> Rows)> Sections =>
        [("created", Created), ("updated", Updated), ("removed", Removed), ("orphans_in_use", OrphansInUse)];
}

/// <summary>
/// Rebuild or repair every copy from `catalog`, and say what differed, as Django's
/// `reconcile_refs` (#13). For use after a data move or a long outage: pages through
/// `catalog`'s `/internal/` list, stores what is missing or older here, and retires what
/// `catalog` no longer has, unless instances still use it.
/// </summary>
public sealed class Reconcile(InstancesDb db, RefService refs, ICatalogClient catalog)
{
    public async Task<ReconcileReport> Run(bool dryRun)
    {
        var report = new ReconcileReport();
        foreach (var kind in new[] { Kinds.QuestionnaireType, Kinds.BatteryType })
        {
            await RunKind(kind, report, dryRun);
        }
        return report;
    }

    async Task RunKind(string kind, ReconcileReport report, bool dryRun)
    {
        var local = kind == Kinds.QuestionnaireType
            ? await db.QuestionnaireTypeRefs.ToDictionaryAsync(t => t.Id, t => t.Version)
            : await db.BatteryTypeRefs.ToDictionaryAsync(t => t.Id, t => t.Version);
        var seen = new HashSet<Guid>();
        await foreach (var snapshot in catalog.Snapshots(kind))
        {
            var refId = Guid.Parse(snapshot.GetProperty("aggregateId").GetString()!);
            seen.Add(refId);
            var label = $"{kind} {refId}";
            if (!local.TryGetValue(refId, out var version))
            {
                report.Created.Add(label);
            }
            else if (version < snapshot.GetProperty("version").GetInt64())
            {
                report.Updated.Add(label);
            }
            else
            {
                continue;
            }
            if (!dryRun)
            {
                await refs.StoreSnapshot(snapshot);
            }
        }

        foreach (var refId in local.Keys.Where(id => !seen.Contains(id)))
        {
            var label = $"{kind} {refId}";
            var inUse = kind == Kinds.QuestionnaireType
                ? await db.Questionnaires.AnyAsync(q => q.QuestionnaireTypeId == refId)
                : await db.Batteries.AnyAsync(b => b.BatteryTypeId == refId);
            if (inUse)
            {
                report.OrphansInUse.Add(label);
                continue;
            }
            report.Removed.Add(label);
            if (!dryRun)
            {
                await refs.Retire(kind, refId);
            }
        }
    }
}
