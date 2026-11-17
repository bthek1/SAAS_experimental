namespace Instances.Api.Data;

// The tables Django created (its models are at `6b47566`), unchanged (#42). Owners live
// in `catalog`, so `OwnerId` is a plain uuid. Every timestamp is UTC. JSON columns are
// `jsonb` held as their text, so nothing in them is ever dropped or renamed.
//
// Django's `on_delete` was never in the database: the foreign keys are NO ACTION, and the
// code deletes in order (RefService, the controllers), as Django's ORM did.

/// <summary>A read-only copy of a `catalog` type, kept current by events (#13).</summary>
public sealed class QuestionnaireTypeRef
{
    public Guid Id { get; set; }
    public string Title { get; set; } = "";
    public DateTime CreatedAt { get; set; }
    public DateTime UpdatedAt { get; set; }
    public long Version { get; set; }
    public Guid OwnerId { get; set; }
    public string QuestionnaireJson { get; set; } = "{}";
}

public sealed class BatteryTypeRef
{
    public Guid Id { get; set; }
    public string Title { get; set; } = "";
    public DateTime CreatedAt { get; set; }
    public DateTime UpdatedAt { get; set; }
    public long Version { get; set; }
    public Guid OwnerId { get; set; }
    public string Description { get; set; } = "";
    public List<BatteryTypeRefSlot> Slots { get; set; } = [];
}

/// <summary>A plain uuid, not a foreign key: a battery type's event can arrive first.</summary>
public sealed class BatteryTypeRefSlot
{
    public long Id { get; set; }
    public Guid QuestionnaireTypeId { get; set; }
    public int Order { get; set; }
    public Guid BatteryTypeId { get; set; }
}

/// <summary>Stops a late event from bringing back a copy of a deleted type.</summary>
public sealed class RetiredRef
{
    public long Id { get; set; }
    public string Kind { get; set; } = "";
    public Guid RefId { get; set; }
    public DateTime RetiredAt { get; set; }
}

/// <summary>
/// Who may no longer reach this service. A reactivated owner keeps a row with `Blocked`
/// off, so an older deactivation arriving late cannot block them again; a deleted owner's
/// stays blocked.
/// </summary>
public sealed class BlockedOwner
{
    public Guid OwnerId { get; set; }
    public bool Blocked { get; set; }
    public bool Deleted { get; set; }
    public long Version { get; set; }
}

public sealed class Battery
{
    public Guid Id { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime UpdatedAt { get; set; }
    public Guid OwnerId { get; set; }
    public string Name { get; set; } = "";
    public Guid ShareToken { get; set; }
    public Guid BatteryTypeId { get; set; }
    public BatteryTypeRef BatteryType { get; set; } = null!;
    public List<Questionnaire> Questionnaires { get; set; } = [];
}

public sealed class Questionnaire
{
    public Guid Id { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime UpdatedAt { get; set; }
    public Guid OwnerId { get; set; }
    public int? BatteryOrder { get; set; }
    public string Name { get; set; } = "";
    public Guid ShareToken { get; set; }
    public string AnswersJson { get; set; } = "{}";
    public string QuestionnaireJsonSnapshot { get; set; } = "{}";
    public string MetricsJson { get; set; } = "{}";
    public DateTime? SubmittedAt { get; set; }
    public Guid? BatteryId { get; set; }
    public Battery? Battery { get; set; }
    public Guid QuestionnaireTypeId { get; set; }
    public QuestionnaireTypeRef QuestionnaireType { get; set; } = null!;
}

public static class Kinds
{
    public const string QuestionnaireType = "questionnaire_type";
    public const string BatteryType = "battery_type";

    public static bool IsKnown(string kind) => kind is QuestionnaireType or BatteryType;
}
