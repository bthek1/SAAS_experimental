using Instances.Api.Auth;
using Instances.Api.Caching;
using Instances.Api.Dashboard;
using Instances.Api.Data;
using Instances.Api.Http;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Instances.Api.Api;

/// <summary>
/// The dashboards, cached per owner (#11, #19). Auth and validation run first, so a blocked
/// owner or a foreign type is refused on a hit too. New questionnaires and submissions
/// reach a cached dashboard within <see cref="CacheFor"/>: invalidating on them would leave
/// little to hit under write-heavy traffic.
/// </summary>
[Authorize]
[Route("api/dashboard")]
public sealed class DashboardController(DashboardService dashboard, OwnedRefs ownedRefs, Cache cache) : ControllerBase
{
    static readonly TimeSpan CacheFor = TimeSpan.FromSeconds(30);
    static readonly Dictionary<string, int> DayChoices = new() { ["7"] = 7, ["30"] = 30, ["90"] = 90 };

    Guid Owner => User.OwnerId();

    [HttpGet("")]
    public async Task<IActionResult> Summary()
    {
        var (days, typeId, zone) = await Parameters(typeRequired: false);
        var body = await cache.Cached(
            "dashboard",
            Owner,
            new { days, questionnaireType = typeId, tz = zone.Id },
            CacheFor,
            async () => ApiJson.Serialize(await dashboard.Summary(Owner, days, typeId, zone)));
        return new ApiResult(200, body);
    }

    [HttpGet("scores")]
    public async Task<IActionResult> Scores()
    {
        var (days, typeId, zone) = await Parameters(typeRequired: true);
        var body = await cache.Cached(
            "dashboard-scores",
            Owner,
            new { days, questionnaireType = typeId, tz = zone.Id },
            CacheFor,
            async () => ApiJson.Serialize(await dashboard.Scores(Owner, typeId!.Value, days, zone)),
            version: 2);
        return new ApiResult(200, body);
    }

    async Task<(int? Days, Guid? TypeId, TimeZoneInfo Zone)> Parameters(bool typeRequired)
    {
        var errors = new FieldErrors();

        int? days = null;
        if (Query.Get(Request, "days") is { } daysText)
        {
            if (DayChoices.TryGetValue(daysText, out var choice))
            {
                days = choice;
            }
            else
            {
                errors.Add("days", $"\"{daysText}\" is not a valid choice.");
            }
        }

        Guid? typeId = null;
        if (Query.Get(Request, "questionnaireType") is { } typeText)
        {
            typeId = await ownedRefs.Resolve(typeText, Kinds.QuestionnaireType, "questionnaireType", Owner, errors);
        }
        else if (typeRequired)
        {
            errors.Add("questionnaireType", Messages.Required);
        }

        var zone = TimeZoneInfo.Utc;
        if (Query.Get(Request, "tz") is { } raw)
        {
            var name = raw.Trim();
            if (name.Length == 0)
            {
                errors.Add("tz", Messages.NotBlank);
            }
            else if (name.Length > Zones.MaxLength)
            {
                errors.Add("tz", $"Ensure this field has no more than {Zones.MaxLength} characters.");
            }
            else if (Zones.Find(name) is { } found)
            {
                zone = found;
            }
            else
            {
                errors.Add("tz", "Unknown time zone.");
            }
        }
        errors.ThrowIfAny();
        return (days, typeId, zone);
    }
}
