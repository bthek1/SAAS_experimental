using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Instances.Api.Data;
using Instances.Api.Http;
using Microsoft.EntityFrameworkCore;

namespace Instances.Api.Commands;

public sealed record SeedResult(int OwnersSeeded, int OwnersSkipped, int Batteries, int Questionnaires, int Submitted);

/// <summary>
/// A realistic dataset for load tests (#9), as Django's `seeding.py` makes it. Runs after
/// `catalog`'s seeder, whose events create the copies this reads: every owner with an
/// "Intake battery" gets batteries and standalone questionnaires created over the last 90
/// days, about 70 % submitted. An owner who already has questionnaires is left as is.
///
/// Python's `random` cannot be reproduced here, so row contents differ from the Django
/// seeder's while the shape (counts, spread, share submitted) is the same (#43).
/// </summary>
public sealed class Seeding(InstancesDb db)
{
    const int SpanDays = 90;
    const double SubmittedShare = 0.7;
    const double BatteryShare = 0.2; // of each owner's questionnaires, two per battery
    static readonly string[] Severities = ["Minimal", "Mild", "Moderate", "Severe"];

    public async Task<SeedResult> Seed(int questionnairesPerOwner, int seed, DateTime? now = null)
    {
        var at = now ?? ApiJson.UtcNow();
        var owners = await db.BatteryTypeRefs.Where(t => t.Title == "Intake battery")
            .OrderBy(t => t.OwnerId).Select(t => t.OwnerId).ToListAsync();
        int seeded = 0, skipped = 0, batteries = 0, questionnaires = 0, submitted = 0;
        foreach (var ownerId in owners)
        {
            if (await db.Questionnaires.AnyAsync(q => q.OwnerId == ownerId))
            {
                skipped++;
                continue;
            }
            // One generator per owner, so adding owners never changes earlier ones.
            var rng = new Random(StableSeed($"{seed}-{ownerId}"));
            var (b, q, s) = await SeedOwner(ownerId, questionnairesPerOwner, rng, at);
            batteries += b;
            questionnaires += q;
            submitted += s;
            seeded++;
        }
        return new SeedResult(seeded, skipped, batteries, questionnaires, submitted);
    }

    async Task<(int Batteries, int Questionnaires, int Submitted)> SeedOwner(Guid ownerId, int count, Random rng, DateTime now)
    {
        var types = await db.QuestionnaireTypeRefs.AsNoTracking()
            .Where(t => t.OwnerId == ownerId && t.Title.StartsWith("Scale "))
            .OrderBy(t => t.Title).ToListAsync();
        var batteryType = await db.BatteryTypeRefs.AsNoTracking()
            .SingleAsync(t => t.OwnerId == ownerId && t.Title == "Intake battery");

        DateTime CreatedAt() => now - TimeSpan.FromSeconds(rng.NextDouble() * SpanDays * 86400);

        var batteries = Enumerable.Range(0, (int)(count * BatteryShare) / 2).Select(i =>
        {
            var created = Micro(CreatedAt());
            return new Battery
            {
                Id = Guid.NewGuid(),
                OwnerId = ownerId,
                BatteryTypeId = batteryType.Id,
                Name = $"Battery {i + 1}",
                ShareToken = Guid.NewGuid(),
                CreatedAt = created,
                UpdatedAt = now,
            };
        }).ToList();

        var rows = new List<Questionnaire>();
        foreach (var (battery, i) in batteries.Select((b, i) => (b, i)))
        {
            foreach (var (type, order) in types.Take(2).Select((t, o) => (t, o)))
            {
                rows.Add(Row(ownerId, type, $"Respondent {i + 1}", battery.CreatedAt, now, battery.Id, order));
            }
        }
        var standalone = count - rows.Count;
        for (var i = 0; i < standalone; i++)
        {
            var type = types[rng.Next(types.Count)];
            rows.Add(Row(ownerId, type, $"Respondent {batteries.Count + i + 1}", Micro(CreatedAt()), now, null, null));
        }

        var submitted = 0;
        foreach (var row in rows)
        {
            if (rng.NextDouble() >= SubmittedShare)
            {
                continue;
            }
            var at = row.CreatedAt + TimeSpan.FromHours(0.5 + rng.NextDouble() * 71.5);
            row.SubmittedAt = Micro(at < now ? at : now);
            var (answers, metrics) = Response(rng);
            row.AnswersJson = answers;
            row.MetricsJson = metrics;
            row.QuestionnaireJsonSnapshot = types.Single(t => t.Id == row.QuestionnaireTypeId).QuestionnaireJson;
            submitted++;
        }

        await using var transaction = await db.Database.BeginTransactionAsync();
        db.Batteries.AddRange(batteries);
        db.Questionnaires.AddRange(rows);
        await db.SaveChangesAsync();
        await transaction.CommitAsync();
        db.ChangeTracker.Clear();
        return (batteries.Count, rows.Count, submitted);
    }

    static Questionnaire Row(Guid ownerId, QuestionnaireTypeRef type, string name, DateTime created, DateTime now, Guid? batteryId, int? order) => new()
    {
        Id = Guid.NewGuid(),
        OwnerId = ownerId,
        QuestionnaireTypeId = type.Id,
        BatteryId = batteryId,
        BatteryOrder = order,
        Name = name,
        ShareToken = Guid.NewGuid(),
        CreatedAt = created,
        UpdatedAt = now,
    };

    static (string Answers, string Metrics) Response(Random rng)
    {
        int a = rng.Next(1, 6), b = rng.Next(1, 6);
        var total = a + b;
        var metrics = new Dictionary<string, object>
        {
            ["total"] = total,
            ["severity"] = Severities[Math.Min((total - 2) / 2, 3)],
            ["flag"] = a > 4,
        };
        return (JsonSerializer.Serialize(new { a, b }), JsonSerializer.Serialize(metrics));
    }

    static DateTime Micro(DateTime value) => new(value.Ticks - value.Ticks % 10, DateTimeKind.Utc);

    static int StableSeed(string text) => BitConverter.ToInt32(SHA256.HashData(Encoding.UTF8.GetBytes(text)), 0);
}
