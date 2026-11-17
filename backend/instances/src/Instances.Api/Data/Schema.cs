using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;

namespace Instances.Api.Data;

/// <summary>
/// The schema stays Django's (#42). The baseline migration is Django's DDL; a database that
/// Django already built is adopted, by recording the baseline as applied, and only later
/// migrations run on it. Django can still run on the same database until #45.
/// </summary>
public static class Schema
{
    public const string Baseline = "20261113065646_Baseline";

    public static async Task<string> Migrate(InstancesDb db)
    {
        var adopted = false;
        var built = await db.Database.SqlQuery<bool>($"""
            SELECT to_regclass('public.questionnaires_questionnaire') IS NOT NULL AS "Value"
            """).SingleAsync();
        var history = db.GetService<Microsoft.EntityFrameworkCore.Migrations.IHistoryRepository>();
        var applied = await db.Database.GetAppliedMigrationsAsync();
        if (built && !applied.Contains(Baseline))
        {
            await db.Database.ExecuteSqlRawAsync(history.GetCreateIfNotExistsScript());
            var product = typeof(DbContext).Assembly
                .GetCustomAttributes(typeof(System.Reflection.AssemblyInformationalVersionAttribute), false)
                .OfType<System.Reflection.AssemblyInformationalVersionAttribute>().First().InformationalVersion.Split('+')[0];
            await db.Database.ExecuteSqlRawAsync(history.GetInsertScript(new(Baseline, product)));
            adopted = true;
        }
        var pending = (await db.Database.GetPendingMigrationsAsync()).ToList();
        await db.Database.MigrateAsync();
        return (adopted ? "adopted a database Django built; " : "")
            + (pending.Count == 0 ? "no migrations to apply" : $"applied {string.Join(", ", pending)}");
    }
}
