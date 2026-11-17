package store_test

import (
	"context"
	"os"
	"strings"
	"testing"

	"instances/internal/store"
	"instances/internal/testdb"
)

func TestMain(m *testing.M) {
	code := m.Run()
	testdb.StopShared()
	os.Exit(code)
}

func TestMigrateBuildsThenSaysNothingToDo(t *testing.T) {
	server := testdb.Start(t)
	ctx := context.Background()
	pool, err := store.Open(ctx, server.Database(t), 2)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()

	first, err := store.Migrate(ctx, pool)
	if err != nil || first != "applied "+store.Baseline {
		t.Fatalf("first migrate: %q, %v", first, err)
	}
	again, err := store.Migrate(ctx, pool)
	if err != nil || again != "no migrations to apply" {
		t.Fatalf("second migrate: %q, %v", again, err)
	}
	var version string
	if err := pool.QueryRow(ctx, `SELECT "ProductVersion" FROM "__EFMigrationsHistory"`).Scan(&version); err != nil {
		t.Fatal(err)
	}
	if version == "" {
		t.Fatal("EF's history row has no product version")
	}
}

func TestMigrateAdoptsATableWithoutHistory(t *testing.T) {
	server := testdb.Start(t)
	ctx := context.Background()
	pool, _ := server.Migrated(t)
	if _, err := pool.Exec(ctx, `DROP TABLE "__EFMigrationsHistory"`); err != nil {
		t.Fatal(err)
	}
	message, err := store.Migrate(ctx, pool)
	if err != nil || !strings.Contains(message, "adopted a database Django built") {
		t.Fatalf("adopt: %q, %v", message, err)
	}
}

func TestMigrateRefusesASchemaNewerThanItKnows(t *testing.T) {
	server := testdb.Start(t)
	ctx := context.Background()
	pool, _ := server.Migrated(t)
	if _, err := pool.Exec(ctx, `INSERT INTO "__EFMigrationsHistory" VALUES ('20991231000000_Later', '10.0.15')`); err != nil {
		t.Fatal(err)
	}
	_, err := store.Migrate(ctx, pool)
	if err == nil || !strings.Contains(err.Error(), "20991231000000_Later") {
		t.Fatalf("expected a refusal naming the migration, got %v", err)
	}
}

func TestConfigReadsOnlySslmode(t *testing.T) {
	config, err := store.Config("pgsql://u:p%40ss@db:6000/name?sslmode=Disable&other=1", 7)
	if err != nil {
		t.Fatal(err)
	}
	c := config.ConnConfig
	if c.Host != "db" || c.Port != 6000 || c.Database != "name" || c.User != "u" || c.Password != "p@ss" {
		t.Fatalf("parsed %+v", c)
	}
	if config.MaxConns != 7 || c.RuntimeParams["timezone"] != "UTC" || c.RuntimeParams["client_encoding"] != "UTF8" {
		t.Fatalf("pool %d, params %v", config.MaxConns, c.RuntimeParams)
	}
	if _, err := store.Config("mysql://x/y", 1); err == nil {
		t.Fatal("a MySQL URL was accepted")
	}
}
