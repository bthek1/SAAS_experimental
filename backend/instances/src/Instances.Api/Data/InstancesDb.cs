using System.Text;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;
using Microsoft.EntityFrameworkCore.Metadata;

namespace Instances.Api.Data;

/// <summary>
/// The `questionnaires_*` tables as Django named them, column for column, index for index,
/// so a migration made from this model diffs against the real schema. The baseline
/// migration is Django's own DDL; `tests/instances_django_schema.txt` is the reference.
/// </summary>
public sealed class InstancesDb(DbContextOptions<InstancesDb> options) : DbContext(options)
{
    public DbSet<QuestionnaireTypeRef> QuestionnaireTypeRefs => Set<QuestionnaireTypeRef>();
    public DbSet<BatteryTypeRef> BatteryTypeRefs => Set<BatteryTypeRef>();
    public DbSet<BatteryTypeRefSlot> BatteryTypeRefSlots => Set<BatteryTypeRefSlot>();
    public DbSet<RetiredRef> RetiredRefs => Set<RetiredRef>();
    public DbSet<BlockedOwner> BlockedOwners => Set<BlockedOwner>();
    public DbSet<Battery> Batteries => Set<Battery>();
    public DbSet<Questionnaire> Questionnaires => Set<Questionnaire>();

    protected override void OnModelCreating(ModelBuilder model)
    {
        model.Entity<QuestionnaireTypeRef>(e =>
        {
            e.ToTable("questionnaires_questionnairetyperef", t =>
                t.HasCheckConstraint("questionnaires_questionnairetyperef_version_check", "version >= 0"));
            e.HasKey(x => x.Id).HasName("questionnaires_questionnairetyperef_pkey");
            e.Property(x => x.Id).ValueGeneratedNever();
            e.Property(x => x.Title).HasMaxLength(255);
            e.Property(x => x.QuestionnaireJson).HasColumnType("jsonb");
            e.HasIndex(x => x.OwnerId).HasDatabaseName("questionnaires_questionnairetyperef_owner_id_5181ab5c");
            e.HasIndex(x => new { x.OwnerId, x.CreatedAt }).IsDescending(false, true)
                .HasDatabaseName("questionnai_owner_i_91d239_idx");
        });

        model.Entity<BatteryTypeRef>(e =>
        {
            e.ToTable("questionnaires_batterytyperef", t =>
                t.HasCheckConstraint("questionnaires_batterytyperef_version_check", "version >= 0"));
            e.HasKey(x => x.Id).HasName("questionnaires_batterytyperef_pkey");
            e.Property(x => x.Id).ValueGeneratedNever();
            e.Property(x => x.Title).HasMaxLength(255);
            e.Property(x => x.Description).HasColumnType("text");
            e.HasIndex(x => x.OwnerId).HasDatabaseName("questionnaires_batterytyperef_owner_id_ec7ca293");
            e.HasIndex(x => new { x.OwnerId, x.CreatedAt }).IsDescending(false, true)
                .HasDatabaseName("questionnai_owner_i_d35b99_idx");
            e.HasMany(x => x.Slots).WithOne().HasForeignKey(x => x.BatteryTypeId)
                .HasConstraintName("questionnaires_batte_battery_type_id_284d3d14_fk_questionn")
                .OnDelete(DeleteBehavior.NoAction);
        });

        model.Entity<BatteryTypeRefSlot>(e =>
        {
            e.ToTable("questionnaires_batterytyperefslot", t =>
                t.HasCheckConstraint("questionnaires_batterytyperefslot_order_check", "\"order\" >= 0"));
            e.HasKey(x => x.Id).HasName("questionnaires_batterytyperefslot_pkey");
            e.Property(x => x.Id).UseIdentityByDefaultColumn();
            e.HasAlternateKey(x => new { x.BatteryTypeId, x.Order })
                .HasName("questionnaires_batteryty_battery_type_id_order_65f5d1de_uniq");
            e.HasIndex(x => x.QuestionnaireTypeId)
                .HasDatabaseName("questionnaires_batterytype_questionnaire_type_id_d4b674bd");
            e.HasIndex(x => x.BatteryTypeId)
                .HasDatabaseName("questionnaires_batterytyperefslot_battery_type_id_284d3d14");
        });

        model.Entity<RetiredRef>(e =>
        {
            e.ToTable("questionnaires_retiredref");
            e.HasKey(x => x.Id).HasName("questionnaires_retiredref_pkey");
            e.Property(x => x.Id).UseIdentityByDefaultColumn();
            e.Property(x => x.Kind).HasMaxLength(32);
            e.HasAlternateKey(x => new { x.Kind, x.RefId }).HasName("retired_ref_once");
        });

        model.Entity<BlockedOwner>(e =>
        {
            e.ToTable("questionnaires_blockedowner", t =>
                t.HasCheckConstraint("questionnaires_blockedowner_version_check", "version >= 0"));
            e.HasKey(x => x.OwnerId).HasName("questionnaires_blockedowner_pkey");
            e.Property(x => x.OwnerId).ValueGeneratedNever();
        });

        model.Entity<Battery>(e =>
        {
            e.ToTable("questionnaires_battery");
            e.HasKey(x => x.Id).HasName("questionnaires_battery_pkey");
            e.Property(x => x.Id).ValueGeneratedNever();
            e.Property(x => x.Name).HasMaxLength(255);
            e.HasAlternateKey(x => x.ShareToken).HasName("questionnaires_battery_share_token_key");
            e.HasIndex(x => x.OwnerId).HasDatabaseName("questionnaires_battery_owner_id_43cde906");
            e.HasIndex(x => x.BatteryTypeId).HasDatabaseName("questionnaires_battery_battery_type_id_8895d766");
            e.HasIndex(x => new { x.OwnerId, x.CreatedAt }).IsDescending(false, true)
                .HasDatabaseName("questionnai_owner_i_29bbb3_idx");
            e.HasOne(x => x.BatteryType).WithMany().HasForeignKey(x => x.BatteryTypeId)
                .HasConstraintName("questionnaires_batte_battery_type_id_8895d766_fk_questionn")
                .OnDelete(DeleteBehavior.NoAction);
        });

        model.Entity<Questionnaire>(e =>
        {
            e.ToTable("questionnaires_questionnaire", t =>
                t.HasCheckConstraint("questionnaires_questionnaire_battery_order_check", "battery_order >= 0"));
            e.HasKey(x => x.Id).HasName("questionnaires_questionnaire_pkey");
            e.Property(x => x.Id).ValueGeneratedNever();
            e.Property(x => x.Name).HasMaxLength(255);
            e.Property(x => x.AnswersJson).HasColumnType("jsonb");
            e.Property(x => x.QuestionnaireJsonSnapshot).HasColumnType("jsonb");
            e.Property(x => x.MetricsJson).HasColumnType("jsonb");
            e.HasAlternateKey(x => x.ShareToken).HasName("questionnaires_questionnaire_share_token_key");
            e.HasIndex(x => x.OwnerId).HasDatabaseName("questionnaires_questionnaire_owner_id_3737fcbb");
            e.HasIndex(x => x.BatteryId).HasDatabaseName("questionnaires_questionnaire_battery_id_fb04baeb");
            e.HasIndex(x => x.QuestionnaireTypeId)
                .HasDatabaseName("questionnaires_questionnaire_questionnaire_type_id_4709d858");
            e.HasIndex(x => new { x.OwnerId, x.CreatedAt }).IsDescending(false, true)
                .HasDatabaseName("questionnai_owner_i_23d4ff_idx");
            // Partial: most dashboard reads only want submitted rows.
            e.HasIndex(x => new { x.OwnerId, x.SubmittedAt }).IsDescending(false, true)
                .HasFilter("(submitted_at IS NOT NULL)").HasDatabaseName("q_owner_submitted");
            e.HasIndex(x => new { x.OwnerId, x.QuestionnaireTypeId, x.SubmittedAt }).IsDescending(false, false, true)
                .HasFilter("(submitted_at IS NOT NULL)").HasDatabaseName("q_owner_type_submitted");
            e.HasOne(x => x.Battery).WithMany(x => x.Questionnaires).HasForeignKey(x => x.BatteryId)
                .HasConstraintName("questionnaires_quest_battery_id_fb04baeb_fk_questionn")
                .OnDelete(DeleteBehavior.NoAction);
            e.HasOne(x => x.QuestionnaireType).WithMany().HasForeignKey(x => x.QuestionnaireTypeId)
                .HasConstraintName("questionnaires_quest_questionnaire_type_i_4709d858_fk_questionn")
                .OnDelete(DeleteBehavior.NoAction);
        });

        foreach (var entity in model.Model.GetEntityTypes())
        {
            foreach (var property in entity.GetProperties())
            {
                property.SetColumnName(SnakeCase(property.Name));
            }
        }
    }

    static string SnakeCase(string name)
    {
        var builder = new StringBuilder();
        for (var i = 0; i < name.Length; i++)
        {
            if (char.IsUpper(name[i]) && i > 0)
            {
                builder.Append('_');
            }
            builder.Append(char.ToLowerInvariant(name[i]));
        }
        return builder.ToString();
    }
}

/// <summary>For `dotnet ef`: a model needs no database.</summary>
public sealed class DesignTimeFactory : IDesignTimeDbContextFactory<InstancesDb>
{
    public InstancesDb CreateDbContext(string[] args) => new(
        new DbContextOptionsBuilder<InstancesDb>()
            .UseNpgsql("Host=localhost;Database=design")
            .Options);
}
