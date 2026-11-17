using System.Text.Json.Serialization;
using Instances.Api.Http;

namespace Instances.Api.Dashboard;

// The dashboard bodies, as Django's `dashboard.py` built them. `range` carries the requested
// zone's offset; every other timestamp is UTC, as elsewhere.

public sealed record SummaryOut(
    RangeOut Range,
    KpisOut Kpis,
    IReadOnlyList<DayOut> SubmissionsByDay,
    [property: JsonPropertyName("byQuestionnaireType")] IReadOnlyList<TypeCountOut> ByQuestionnaireType,
    IReadOnlyList<BatteryTypeCountOut> ByBatteryType,
    IReadOnlyList<RecentOut> RecentSubmissions,
    IReadOnlyList<StaleOut> StalePending);

public sealed record RangeOut(
    int? Days,
    [property: JsonPropertyName("from")] DateTimeOffset? From,
    DateTimeOffset To);

public sealed record KpisOut(
    int QuestionnairesSent,
    int QuestionnairesSubmitted,
    int QuestionnairesPending,
    double CompletionRate,
    double? MedianHoursToComplete,
    int BatteriesTotal,
    int BatteriesComplete,
    int BatteriesInProgress,
    int BatteriesNotStarted);

public sealed record DayOut(DateOnly Date, int Count);

public sealed record TypeCountOut(Guid Id, string Title, int Sent, int Submitted, int Pending);

public sealed record BatteryTypeCountOut(Guid Id, string Title, int Complete, int InProgress, int NotStarted);

public sealed record RecentOut(Guid Id, string Name, string QuestionnaireTypeTitle, DateTime SubmittedAt);

public sealed record StaleOut(Guid Id, string Name, string QuestionnaireTypeTitle, Guid ShareToken, DateTime CreatedAt, int AgeDays);

public sealed record ScoresOut(Guid QuestionnaireTypeId, IReadOnlyList<MetricOut> Metrics);

public sealed record MetricOut(
    string Name,
    string Label,
    string Kind,
    int Count,
    IReadOnlyList<PointOut> Points,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] double? Mean,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] IReadOnlyList<DistributionOut>? Distribution);

public sealed record PointOut(Guid QuestionnaireId, string Name, DateTime SubmittedAt, RawJson Value);

public sealed record DistributionOut(RawJson Value, int Count);
