package store

import (
	"context"
	_ "embed"
	"fmt"
	"slices"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// The schema is Django's, and instances_NET's EF migrations own it (#42). This service
// never adds a migration of its own (#52): it builds the baseline on an empty database,
// adopts a database Django or .NET built, and refuses one that is newer than it knows.
// It records what it did in EF's own history table, so .NET can take any of them over.
const (
	Baseline = "20261113065646_Baseline"
	// What EF records beside each migration it applies (the model snapshot's version).
	efProductVersion = "10.0.15"
)

// Known lists every migration this service's code matches, oldest first. A schema change
// lands in instances_NET first; add its id here only once this code reads that schema.
var Known = []string{Baseline}

//go:embed baseline.sql
var baselineSQL string

const historyDDL = `CREATE TABLE IF NOT EXISTS "__EFMigrationsHistory" (
    "MigrationId" character varying(150) NOT NULL,
    "ProductVersion" character varying(32) NOT NULL,
    CONSTRAINT "PK___EFMigrationsHistory" PRIMARY KEY ("MigrationId")
)`

// Migrate brings the database to the baseline and says what it did, as `Instances.Api.dll
// migrate` words it, so the same checks read either.
func Migrate(ctx context.Context, pool *pgxpool.Pool) (string, error) {
	var message string
	err := pgx.BeginFunc(ctx, pool, func(tx pgx.Tx) error {
		if _, err := tx.Exec(ctx, historyDDL); err != nil {
			return err
		}
		// One migrate at a time, as EF does.
		if _, err := tx.Exec(ctx, `LOCK TABLE "__EFMigrationsHistory" IN ACCESS EXCLUSIVE MODE`); err != nil {
			return err
		}
		var built bool
		if err := tx.QueryRow(ctx,
			`SELECT to_regclass('public.questionnaires_questionnaire') IS NOT NULL`).Scan(&built); err != nil {
			return err
		}
		rows, err := tx.Query(ctx, `SELECT "MigrationId" FROM "__EFMigrationsHistory" ORDER BY "MigrationId"`)
		if err != nil {
			return err
		}
		applied, err := pgx.CollectRows(rows, pgx.RowTo[string])
		if err != nil {
			return err
		}
		for _, id := range applied {
			if !slices.Contains(Known, id) {
				return fmt.Errorf("this database has migration %s, which instances_GO does not know "+
					"(it knows %s): update instances_GO before running it here", id, strings.Join(Known, ", "))
			}
		}
		record := func() error {
			_, err := tx.Exec(ctx, `INSERT INTO "__EFMigrationsHistory" ("MigrationId", "ProductVersion") VALUES ($1, $2)`,
				Baseline, efProductVersion)
			return err
		}
		switch {
		case slices.Contains(applied, Baseline):
			message = "no migrations to apply"
		case built:
			// Django built it: mark the baseline applied rather than rebuild it.
			message = "adopted a database Django built; no migrations to apply"
			return record()
		default:
			if _, err := tx.Exec(ctx, baselineSQL); err != nil {
				return err
			}
			message = "applied " + Baseline
			return record()
		}
		return nil
	})
	return message, err
}
