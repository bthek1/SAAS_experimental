using Instances.Api.Data;
using Instances.Api.Http;

namespace Instances.Api.Api;

// Response bodies, field for field as Django's serializers wrote them.

public sealed record TypeOut(Guid Id, string Title, RawJson QuestionnaireJson, DateTime CreatedAt, DateTime UpdatedAt);

public sealed record QuestionnaireOut(
    Guid Id,
    Guid QuestionnaireTypeId,
    TypeOut QuestionnaireType,
    Guid? BatteryId,
    int? BatteryOrder,
    string Name,
    Guid ShareToken,
    RawJson Answers,
    RawJson Metrics,
    DateTime? SubmittedAt,
    RawJson QuestionnaireJsonSnapshot,
    DateTime CreatedAt,
    DateTime UpdatedAt)
{
    public static QuestionnaireOut From(Questionnaire q) => new(
        q.Id,
        q.QuestionnaireTypeId,
        new TypeOut(
            q.QuestionnaireType.Id,
            q.QuestionnaireType.Title,
            new RawJson(q.QuestionnaireType.QuestionnaireJson),
            q.QuestionnaireType.CreatedAt,
            q.QuestionnaireType.UpdatedAt),
        q.BatteryId,
        q.BatteryOrder,
        q.Name,
        q.ShareToken,
        new RawJson(q.AnswersJson),
        new RawJson(q.MetricsJson),
        q.SubmittedAt,
        new RawJson(q.QuestionnaireJsonSnapshot),
        q.CreatedAt,
        q.UpdatedAt);
}

public sealed record SlotOut(int? Order, Guid QuestionnaireId, Guid ShareToken, string QuestionnaireTypeName, DateTime? SubmittedAt);

public sealed record BatteryOut(
    Guid Id,
    Guid BatteryTypeId,
    string BatteryTypeName,
    string Name,
    Guid ShareToken,
    IReadOnlyList<SlotOut> Questionnaires,
    bool IsComplete,
    DateTime CreatedAt,
    DateTime UpdatedAt)
{
    public static BatteryOut From(Battery b) => new(
        b.Id,
        b.BatteryTypeId,
        b.BatteryType.Title,
        b.Name,
        b.ShareToken,
        Slots(b).Select(q => new SlotOut(q.BatteryOrder, q.Id, q.ShareToken, q.QuestionnaireType.Title, q.SubmittedAt)).ToList(),
        IsCompleteOf(b),
        b.CreatedAt,
        b.UpdatedAt);

    internal static IEnumerable<Questionnaire> Slots(Battery b) => b.Questionnaires.OrderBy(q => q.BatteryOrder);

    internal static bool IsCompleteOf(Battery b) =>
        b.Questionnaires.Count > 0 && b.Questionnaires.All(q => q.SubmittedAt is not null);
}

// Share-link bodies: only what a respondent needs. No owner, no answers.

public sealed record PublicQuestionnaireOut(
    Guid Id, string Name, string QuestionnaireTypeTitle, RawJson QuestionnaireJson, DateTime? SubmittedAt)
{
    /// <summary>A submitted questionnaire shows the definition it was answered against.</summary>
    public static PublicQuestionnaireOut From(Questionnaire q) => new(
        q.Id,
        q.Name,
        q.QuestionnaireType.Title,
        new RawJson(q.SubmittedAt is not null ? q.QuestionnaireJsonSnapshot : q.QuestionnaireType.QuestionnaireJson),
        q.SubmittedAt);
}

public sealed record PublicSlotOut(int? Order, Guid ShareToken, string QuestionnaireTypeName, DateTime? SubmittedAt);

public sealed record PublicBatteryOut(
    Guid Id, string Name, string BatteryTypeName, IReadOnlyList<PublicSlotOut> Questionnaires, bool IsComplete)
{
    public static PublicBatteryOut From(Battery b) => new(
        b.Id,
        b.Name,
        b.BatteryType.Title,
        BatteryOut.Slots(b).Select(q => new PublicSlotOut(q.BatteryOrder, q.ShareToken, q.QuestionnaireType.Title, q.SubmittedAt)).ToList(),
        BatteryOut.IsCompleteOf(b));
}
