using System.Text.Json;
using Instances.Api.Data;
using Instances.Api.Http;
using Microsoft.EntityFrameworkCore;

namespace Instances.Api.Dashboard;

/// <summary>
/// Owner-scoped aggregates for the dashboard, as Django's `dashboard.py` (#19).
///
/// A window of `days` starts at midnight in `tz`, `days - 1` days ago, so "7" is today plus
/// the six days before it; none means all time. `submissionsByDay` buckets by date in `tz`.
/// KPIs and per-type counts follow a cohort, the questionnaires *created* in the window and
/// how many of those were submitted, whenever; activity (`submissionsByDay`,
/// `recentSubmissions`) counts by `submitted_at`. Pending items older than a week are
/// listed whatever the window. Work on a miss is bounded by the page, not the owner's rows:
/// the database counts, sorts and buckets.
/// </summary>
public sealed class DashboardService(InstancesDb db)
{
    public const int ScorePointLimit = 500;
    const int ListLimit = 10;
    const int StaleAfterDays = 7;

    static DateTimeOffset NowIn(TimeZoneInfo zone) =>
        TimeZoneInfo.ConvertTime(new DateTimeOffset(ApiJson.UtcNow()), zone);

    public static DateTimeOffset? WindowStart(int? days, DateTimeOffset now, TimeZoneInfo zone) =>
        days is { } count
            ? Python.AtWallTime(now.Date.AddDays(-(count - 1)), zone)
            : null;

    public async Task<SummaryOut> Summary(Guid ownerId, int? days, Guid? typeId, TimeZoneInfo zone)
    {
        var now = NowIn(zone);
        var start = WindowStart(days, now, zone);
        var startUtc = start?.UtcDateTime;

        var questionnaires = db.Questionnaires.AsNoTracking().Where(q => q.OwnerId == ownerId);
        var batteries = db.Batteries.AsNoTracking().Where(b => b.OwnerId == ownerId);
        var qtypes = db.QuestionnaireTypeRefs.AsNoTracking().Where(t => t.OwnerId == ownerId);
        var btypes = db.BatteryTypeRefs.AsNoTracking().Where(t => t.OwnerId == ownerId);
        if (typeId is { } type)
        {
            questionnaires = questionnaires.Where(q => q.QuestionnaireTypeId == type);
            // A subquery rather than a join, so the slot counts below still see every
            // questionnaire in the battery, not just the ones of this type.
            batteries = batteries.Where(b =>
                db.Questionnaires.Any(q => q.QuestionnaireTypeId == type && q.BatteryId == b.Id));
            qtypes = qtypes.Where(t => t.Id == type);
            btypes = btypes.Where(t => db.BatteryTypeRefSlots.Any(s => s.QuestionnaireTypeId == type && s.BatteryTypeId == t.Id));
        }

        var cohort = questionnaires;
        var submittedInWindow = questionnaires.Where(q => q.SubmittedAt != null);
        if (startUtc is { } from)
        {
            cohort = cohort.Where(q => q.CreatedAt >= from);
            submittedInWindow = submittedInWindow.Where(q => q.SubmittedAt >= from);
            batteries = batteries.Where(b => b.CreatedAt >= from);
        }

        var counts = await cohort.GroupBy(_ => 1)
            .Select(g => new { Sent = g.Count(), Submitted = g.Count(q => q.SubmittedAt != null) })
            .SingleOrDefaultAsync();
        var sent = counts?.Sent ?? 0;
        var submitted = counts?.Submitted ?? 0;

        var byType = await qtypes.OrderBy(t => t.Title).Select(t => new
        {
            t.Id,
            t.Title,
            Sent = db.Questionnaires.Count(q => q.QuestionnaireTypeId == t.Id && q.OwnerId == ownerId
                && (startUtc == null || q.CreatedAt >= startUtc)),
            Submitted = db.Questionnaires.Count(q => q.QuestionnaireTypeId == t.Id && q.OwnerId == ownerId
                && (startUtc == null || q.CreatedAt >= startUtc) && q.SubmittedAt != null),
        }).ToListAsync();

        // The owner sits on the join: stale planner statistics must not turn this into a
        // scan of every owner's questionnaires.
        var batteryRows = await batteries.Select(b => new
        {
            b.BatteryTypeId,
            Total = db.Questionnaires.Count(q => q.BatteryId == b.Id && q.OwnerId == ownerId),
            Submitted = db.Questionnaires.Count(q => q.BatteryId == b.Id && q.OwnerId == ownerId && q.SubmittedAt != null),
        }).ToListAsync();
        var statusByType = new Dictionary<Guid, BatteryStatus>();
        var batteryKpis = new BatteryStatus();
        foreach (var row in batteryRows)
        {
            var status = Status(row.Total, row.Submitted);
            batteryKpis.Add(status);
            if (!statusByType.TryGetValue(row.BatteryTypeId, out var bucket))
            {
                statusByType[row.BatteryTypeId] = bucket = new BatteryStatus();
            }
            bucket.Add(status);
        }
        var batteryTypes = await btypes.OrderBy(t => t.Title).Select(t => new { t.Id, t.Title }).ToListAsync();

        var recent = await submittedInWindow.OrderByDescending(q => q.SubmittedAt).Take(ListLimit)
            .Select(q => new RecentOut(
                q.Id,
                // Questionnaires made by a battery have no name of their own: show the battery's.
                q.Name != "" ? q.Name : q.Battery != null ? q.Battery.Name : "",
                q.QuestionnaireType.Title,
                q.SubmittedAt!.Value))
            .ToListAsync();

        var staleBefore = Python.WallDaysBefore(now, StaleAfterDays, zone).UtcDateTime;
        var stale = await questionnaires.Where(q => q.SubmittedAt == null && q.CreatedAt < staleBefore)
            .OrderBy(q => q.CreatedAt).Take(ListLimit)
            .Select(q => new
            {
                q.Id,
                Name = q.Name != "" ? q.Name : q.Battery != null ? q.Battery.Name : "",
                Title = q.QuestionnaireType.Title,
                q.ShareToken,
                q.CreatedAt,
            })
            .ToListAsync();
        var nowUtc = now.UtcDateTime;

        return new SummaryOut(
            new RangeOut(days, start, now),
            new KpisOut(
                sent,
                submitted,
                sent - submitted,
                sent > 0 ? Python.Round((double)submitted / sent, 4) : 0.0,
                await MedianHours(cohort.Where(q => q.SubmittedAt != null), submitted),
                batteryKpis.Complete + batteryKpis.InProgress + batteryKpis.NotStarted,
                batteryKpis.Complete,
                batteryKpis.InProgress,
                batteryKpis.NotStarted),
            await SubmissionsByDay(submittedInWindow, start, now, zone),
            byType.Select(t => new TypeCountOut(t.Id, t.Title, t.Sent, t.Submitted, t.Sent - t.Submitted)).ToList(),
            batteryTypes.Select(t =>
            {
                var status = statusByType.GetValueOrDefault(t.Id) ?? new BatteryStatus();
                return new BatteryTypeCountOut(t.Id, t.Title, status.Complete, status.InProgress, status.NotStarted);
            }).ToList(),
            recent,
            stale.Select(s => new StaleOut(
                s.Id, s.Name, s.Title, s.ShareToken, s.CreatedAt, (int)Math.Floor((nowUtc - s.CreatedAt).TotalDays))).ToList());
    }

    static string Status(int total, int submitted) =>
        total > 0 && submitted == total ? "complete" : submitted == 0 ? "notStarted" : "inProgress";

    sealed class BatteryStatus
    {
        public int Complete;
        public int InProgress;
        public int NotStarted;

        public void Add(string status)
        {
            switch (status)
            {
                case "complete": Complete++; break;
                case "inProgress": InProgress++; break;
                default: NotStarted++; break;
            }
        }
    }

    /// <summary>Sorted in the database, so only the middle one or two rows come back.</summary>
    static async Task<double?> MedianHours(IQueryable<Questionnaire> submitted, int count)
    {
        if (count == 0)
        {
            return null;
        }
        var skip = (count - 1) / 2;
        var take = count / 2 + 1 - skip;
        var middle = await submitted.Select(q => q.SubmittedAt!.Value - q.CreatedAt)
            .OrderBy(d => d).Skip(skip).Take(take).ToListAsync();
        if (middle.Count == 0)
        {
            return null;
        }
        var seconds = middle.Sum(d => d.TotalSeconds) / middle.Count;
        return Python.Round(seconds / 3600, 1);
    }

    async Task<IReadOnlyList<DayOut>> SubmissionsByDay(
        IQueryable<Questionnaire> submitted, DateTimeOffset? start, DateTimeOffset now, TimeZoneInfo zone)
    {
        var rows = await submitted
            .GroupBy(q => TimeZoneInfo.ConvertTimeBySystemTimeZoneId(q.SubmittedAt!.Value, zone.Id).Date)
            .Select(g => new { Day = g.Key, Count = g.Count() })
            .ToListAsync();
        var counts = rows.ToDictionary(r => DateOnly.FromDateTime(r.Day), r => r.Count);
        if (counts.Count == 0 && start is null)
        {
            return [];
        }
        var day = start is { } from ? DateOnly.FromDateTime(from.DateTime) : counts.Keys.Min();
        var today = DateOnly.FromDateTime(now.DateTime);
        var series = new List<DayOut>();
        for (; day <= today; day = day.AddDays(1))
        {
            series.Add(new DayOut(day, counts.GetValueOrDefault(day)));
        }
        return series;
    }

    // ── Scores ───────────────────────────────────────────────────────────────

    /// <summary>
    /// Every stored metric of one type's submitted questionnaires, by metric. `count`, `mean`
    /// and `distribution` cover every row in the window; `points` holds only the latest
    /// <see cref="ScorePointLimit"/>. A metric's kind comes from its first value (number,
    /// text or boolean); later values of another kind are skipped. Labels and order follow
    /// the type's current `calculatedValues`, then any names only older snapshots had.
    /// </summary>
    public async Task<ScoresOut> Scores(Guid ownerId, Guid typeId, int? days, TimeZoneInfo zone)
    {
        var start = WindowStart(days, NowIn(zone), zone)?.UtcDateTime;
        var rows = db.Questionnaires.AsNoTracking()
            .Where(q => q.OwnerId == ownerId && q.QuestionnaireTypeId == typeId && q.SubmittedAt != null);
        if (start is { } from)
        {
            rows = rows.Where(q => q.SubmittedAt >= from);
        }
        var definition = await db.QuestionnaireTypeRefs.Where(t => t.Id == typeId)
            .Select(t => t.QuestionnaireJson).SingleAsync();
        var labels = MetricLabels(definition);

        var metrics = new Dictionary<string, MetricTotals>();
        var order = new List<string>();
        await foreach (var stored in rows.OrderBy(q => q.SubmittedAt).ThenBy(q => q.Id)
            .Select(q => q.MetricsJson).AsAsyncEnumerable())
        {
            using var document = JsonDocument.Parse(stored);
            if (document.RootElement.ValueKind != JsonValueKind.Object)
            {
                continue;
            }
            foreach (var property in document.RootElement.EnumerateObject())
            {
                if (Kind(property.Value) is not { } kind)
                {
                    continue;
                }
                if (!metrics.TryGetValue(property.Name, out var totals))
                {
                    metrics[property.Name] = totals = new MetricTotals(kind);
                    order.Add(property.Name);
                }
                totals.Add(property.Value, kind);
            }
        }

        var latest = await rows.OrderByDescending(q => q.SubmittedAt).ThenByDescending(q => q.Id).Take(ScorePointLimit)
            .Select(q => new
            {
                q.Id,
                Name = q.Name != "" ? q.Name : q.Battery != null ? q.Battery.Name : "",
                SubmittedAt = q.SubmittedAt!.Value,
                q.MetricsJson,
            })
            .ToListAsync();
        latest.Reverse();
        var points = metrics.Keys.ToDictionary(name => name, _ => new List<PointOut>());
        foreach (var row in latest)
        {
            using var document = JsonDocument.Parse(row.MetricsJson);
            if (document.RootElement.ValueKind != JsonValueKind.Object)
            {
                continue;
            }
            foreach (var property in document.RootElement.EnumerateObject())
            {
                if (metrics.TryGetValue(property.Name, out var totals) && Kind(property.Value) == totals.Kind)
                {
                    points[property.Name].Add(new PointOut(row.Id, row.Name, row.SubmittedAt, RawJson.From(property.Value)));
                }
            }
        }

        var labelOrder = labels.Keys.ToList();
        var ordered = order
            .OrderBy(name => labelOrder.IndexOf(name) is var index and >= 0 ? index : labelOrder.Count)
            .ThenBy(name => name, StringComparer.Ordinal)
            .Select(name => metrics[name].Out(name, labels.GetValueOrDefault(name, name), points[name]))
            .ToList();
        return new ScoresOut(typeId, ordered);
    }

    /// <summary>A boolean before a number: Python's `True` is an int too.</summary>
    static string? Kind(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.True or JsonValueKind.False => "boolean",
        JsonValueKind.Number => "numeric",
        JsonValueKind.String => "categorical",
        _ => null,
    };

    /// <summary>`calculatedValues` names to display labels, in definition order.</summary>
    static Dictionary<string, string> MetricLabels(string questionnaireJson)
    {
        var labels = new Dictionary<string, string>();
        using var document = JsonDocument.Parse(questionnaireJson);
        if (document.RootElement.ValueKind != JsonValueKind.Object
            || !document.RootElement.TryGetProperty("calculatedValues", out var definitions)
            || definitions.ValueKind != JsonValueKind.Array)
        {
            return labels;
        }
        foreach (var definition in definitions.EnumerateArray())
        {
            if (definition.ValueKind != JsonValueKind.Object
                || !definition.TryGetProperty("name", out var name) || name.ValueKind != JsonValueKind.String)
            {
                continue;
            }
            var key = name.GetString()!;
            labels[key] = definition.TryGetProperty("title", out var title) && Truthy(title)
                ? title.ValueKind == JsonValueKind.String ? title.GetString()! : title.GetRawText()
                : key;
        }
        return labels;
    }

    static bool Truthy(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.String => value.GetString() != "",
        JsonValueKind.Number => value.GetDouble() != 0,
        JsonValueKind.True => true,
        JsonValueKind.Object => value.EnumerateObject().Any(),
        JsonValueKind.Array => value.GetArrayLength() > 0,
        _ => false,
    };

    sealed class MetricTotals(string kind)
    {
        public string Kind { get; } = kind;
        int _count;
        double _sum;
        readonly Dictionary<string, (JsonElement Value, int Count)> _distribution = new(StringComparer.Ordinal);

        public void Add(JsonElement value, string kind)
        {
            if (kind != Kind)
            {
                return;
            }
            _count++;
            if (Kind == "numeric")
            {
                _sum += value.GetDouble();
                return;
            }
            var key = PythonStr(value);
            _distribution[key] = _distribution.TryGetValue(key, out var seen)
                ? (seen.Value, seen.Count + 1)
                : (value.Clone(), 1);
        }

        /// <summary>`str(value)`, which orders the distribution's ties.</summary>
        static string PythonStr(JsonElement value) => value.ValueKind switch
        {
            JsonValueKind.True => "True",
            JsonValueKind.False => "False",
            _ => value.GetString()!,
        };

        public MetricOut Out(string name, string label, IReadOnlyList<PointOut> points) => Kind == "numeric"
            ? new MetricOut(name, label, Kind, _count, points, Python.Round(_sum / _count, 2), null)
            : new MetricOut(name, label, Kind, _count, points, null,
                _distribution
                    .OrderByDescending(item => item.Value.Count)
                    .ThenBy(item => item.Key, StringComparer.Ordinal)
                    .Select(item => new DistributionOut(RawJson.From(item.Value.Value), item.Value.Count))
                    .ToList());
    }
}
