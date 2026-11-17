// Package commands is the binary's verbs besides `migrate` and `health`, as instances_NET's
// Commands/ folder: seed-loadtest, reset-db, clear-cache (the three dev or loadtest only)
// and reconcile-refs.
package commands

import (
	"context"
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"math/rand/v2"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"instances/internal/httpx"
	"instances/internal/refs"
)

// ResetDB empties every questionnaires_ table: `just loadtest-reset`, so every measured run
// starts from the same, empty data.
func ResetDB(ctx context.Context, pool *pgxpool.Pool, out io.Writer) error {
	if _, err := pool.Exec(ctx, `TRUNCATE questionnaires_questionnaire, questionnaires_battery,
		questionnaires_batterytyperefslot, questionnaires_batterytyperef, questionnaires_questionnairetyperef,
		questionnaires_retiredref, questionnaires_blockedowner RESTART IDENTITY`); err != nil {
		return err
	}
	fmt.Fprintln(out, "emptied every questionnaires_ table")
	return nil
}

// Seeding constants, as Django's seeding.py and .NET's Seeding.cs set them.
const (
	spanDays       = 90
	submittedShare = 0.7
	batteryShare   = 0.2 // of each owner's questionnaires, two per battery
)

var severities = []string{"Minimal", "Mild", "Moderate", "Severe"}

// SeedLoadTest makes a realistic dataset for load tests (#9). It runs after `catalog`'s
// seeder, whose events create the copies it reads: every owner with an "Intake battery"
// gets batteries and standalone questionnaires created over the last 90 days, about 70 %
// submitted. An owner who already has questionnaires is left as is. Python's random
// cannot be reproduced, so rows differ from the Django and .NET seeders' while the shape
// (counts, spread, share submitted) is the same.
func SeedLoadTest(ctx context.Context, pool *pgxpool.Pool, perOwner int, seed int, out io.Writer) error {
	now := httpx.Now()
	rows, err := pool.Query(ctx, `SELECT owner_id FROM questionnaires_batterytyperef WHERE title = 'Intake battery'
		ORDER BY owner_id`)
	if err != nil {
		return err
	}
	owners, err := pgx.CollectRows(rows, pgx.RowTo[uuid.UUID])
	if err != nil {
		return err
	}
	var seeded, skipped, batteries, questionnaires, submitted int
	for _, owner := range owners {
		var has bool
		if err := pool.QueryRow(ctx, `SELECT EXISTS (SELECT 1 FROM questionnaires_questionnaire WHERE owner_id = $1)`,
			owner).Scan(&has); err != nil {
			return err
		}
		if has {
			skipped++
			continue
		}
		// One generator per owner, so adding owners never changes earlier ones.
		digest := sha256.Sum256([]byte(fmt.Sprintf("%d-%s", seed, owner)))
		rng := rand.New(rand.NewPCG(binary.LittleEndian.Uint64(digest[:8]), binary.LittleEndian.Uint64(digest[8:16])))
		b, q, s, err := seedOwner(ctx, pool, owner, perOwner, rng, now)
		if err != nil {
			return err
		}
		batteries, questionnaires, submitted, seeded = batteries+b, questionnaires+q, submitted+s, seeded+1
	}
	fmt.Fprintf(out, "owners: %d seeded, %d already there\n", seeded, skipped)
	fmt.Fprintf(out, "batteries: %d, questionnaires: %d (%d submitted)\n", batteries, questionnaires, submitted)
	return nil
}

type scale struct {
	id         uuid.UUID
	definition string
}

type seededRow struct {
	id, typeID, token     uuid.UUID
	batteryID             *uuid.UUID
	order                 *int32
	name                  string
	created               time.Time
	submitted             *time.Time
	answers, metrics, def string
}

func seedOwner(ctx context.Context, pool *pgxpool.Pool, owner uuid.UUID, count int, rng *rand.Rand,
	now time.Time) (int, int, int, error) {
	rows, err := pool.Query(ctx, `SELECT id, questionnaire_json::text FROM questionnaires_questionnairetyperef
		WHERE owner_id = $1 AND title LIKE 'Scale %' ORDER BY title`, owner)
	if err != nil {
		return 0, 0, 0, err
	}
	types, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (scale, error) {
		var s scale
		return s, row.Scan(&s.id, &s.definition)
	})
	if err != nil {
		return 0, 0, 0, err
	}
	if len(types) == 0 {
		return 0, 0, 0, fmt.Errorf("owner %s has no \"Scale\" types", owner)
	}
	var batteryType uuid.UUID
	if err := pool.QueryRow(ctx, `SELECT id FROM questionnaires_batterytyperef WHERE owner_id = $1 AND title = 'Intake battery'`,
		owner).Scan(&batteryType); err != nil {
		return 0, 0, 0, err
	}
	createdAt := func() time.Time {
		return now.Add(-time.Duration(rng.Float64() * spanDays * 86400 * float64(time.Second))).Truncate(time.Microsecond)
	}

	type battery struct {
		id, token uuid.UUID
		name      string
		created   time.Time
	}
	batteries := make([]battery, int(float64(count)*batteryShare)/2)
	var rowsOut []seededRow
	for i := range batteries {
		batteries[i] = battery{uuid.New(), uuid.New(), fmt.Sprintf("Battery %d", i+1), createdAt()}
		for order, t := range types[:min(2, len(types))] {
			o := int32(order)
			id := batteries[i].id
			rowsOut = append(rowsOut, seededRow{id: uuid.New(), typeID: t.id, token: uuid.New(), batteryID: &id,
				order: &o, name: fmt.Sprintf("Respondent %d", i+1), created: batteries[i].created})
		}
	}
	standalone := count - len(rowsOut)
	for i := range standalone {
		t := types[rng.IntN(len(types))]
		rowsOut = append(rowsOut, seededRow{id: uuid.New(), typeID: t.id, token: uuid.New(),
			name: fmt.Sprintf("Respondent %d", len(batteries)+i+1), created: createdAt()})
	}
	definitions := map[uuid.UUID]string{}
	for _, t := range types {
		definitions[t.id] = t.definition
	}
	submitted := 0
	for i := range rowsOut {
		row := &rowsOut[i]
		row.answers, row.metrics, row.def = "{}", "{}", "{}"
		if rng.Float64() >= submittedShare {
			continue
		}
		at := row.created.Add(time.Duration((0.5 + rng.Float64()*71.5) * float64(time.Hour)))
		if at.After(now) {
			at = now
		}
		at = at.Truncate(time.Microsecond)
		row.submitted = &at
		a, b := rng.IntN(5)+1, rng.IntN(5)+1
		total := a + b
		answers, _ := json.Marshal(map[string]int{"a": a, "b": b})
		metrics, _ := json.Marshal(map[string]any{"total": total, "severity": severities[min((total-2)/2, 3)], "flag": a > 4})
		row.answers, row.metrics, row.def = string(answers), string(metrics), definitions[row.typeID]
		submitted++
	}

	err = pgx.BeginFunc(ctx, pool, func(tx pgx.Tx) error {
		for _, b := range batteries {
			if _, err := tx.Exec(ctx, `INSERT INTO questionnaires_battery
				    (id, created_at, updated_at, owner_id, name, share_token, battery_type_id)
				VALUES ($1, $2, $3, $4, $5, $6, $7)`, b.id, b.created, now, owner, b.name, b.token, batteryType); err != nil {
				return err
			}
		}
		_, err := tx.CopyFrom(ctx, pgx.Identifier{"questionnaires_questionnaire"},
			[]string{"id", "created_at", "updated_at", "owner_id", "battery_order", "name", "share_token", "answers_json",
				"questionnaire_json_snapshot", "metrics_json", "submitted_at", "battery_id", "questionnaire_type_id"},
			pgx.CopyFromSlice(len(rowsOut), func(i int) ([]any, error) {
				r := rowsOut[i]
				return []any{r.id, r.created, now, owner, r.order, r.name, r.token, r.answers, r.def, r.metrics,
					r.submitted, r.batteryID, r.typeID}, nil
			}))
		return err
	})
	return len(batteries), len(rowsOut), submitted, err
}

// Reconcile rebuilds or repairs every copy from `catalog`, and says what differed, as
// Django's reconcile_refs (#13). For use after a data move or a long outage: pages
// through `catalog`'s `/internal/` list, stores what is missing or older here, and
// retires what `catalog` no longer has, unless instances still use it.
func Reconcile(ctx context.Context, service *refs.Service, dryRun bool, out io.Writer) error {
	sections := []struct {
		name string
		rows []string
	}{{name: "created"}, {name: "updated"}, {name: "removed"}, {name: "orphans_in_use"}}
	for _, kind := range []string{refs.QuestionnaireType, refs.BatteryType} {
		table := "questionnaires_questionnairetyperef"
		if kind == refs.BatteryType {
			table = "questionnaires_batterytyperef"
		}
		rows, err := service.Pool.Query(ctx, `SELECT id, version FROM `+table)
		if err != nil {
			return err
		}
		local := map[uuid.UUID]int64{}
		var order []uuid.UUID
		for rows.Next() {
			var id uuid.UUID
			var version int64
			if err := rows.Scan(&id, &version); err != nil {
				rows.Close()
				return err
			}
			local[id] = version
			order = append(order, id)
		}
		if err := rows.Err(); err != nil {
			return err
		}
		seen := map[uuid.UUID]bool{}
		err = service.Catalog.Snapshots(ctx, kind, func(snapshot json.RawMessage) error {
			var envelope struct {
				AggregateID uuid.UUID `json:"aggregateId"`
				Version     int64     `json:"version"`
			}
			if err := json.Unmarshal(snapshot, &envelope); err != nil {
				return err
			}
			seen[envelope.AggregateID] = true
			label := fmt.Sprintf("%s %s", kind, envelope.AggregateID)
			version, present := local[envelope.AggregateID]
			switch {
			case !present:
				sections[0].rows = append(sections[0].rows, label)
			case version < envelope.Version:
				sections[1].rows = append(sections[1].rows, label)
			default:
				return nil
			}
			if dryRun {
				return nil
			}
			return service.StoreSnapshot(ctx, snapshot)
		})
		if err != nil {
			return err
		}
		for _, id := range order {
			if seen[id] {
				continue
			}
			label := fmt.Sprintf("%s %s", kind, id)
			used, err := service.InUse(ctx, kind, id)
			if err != nil {
				return err
			}
			if used {
				sections[3].rows = append(sections[3].rows, label)
				continue
			}
			sections[2].rows = append(sections[2].rows, label)
			if !dryRun {
				if err := service.Retire(ctx, kind, id); err != nil {
					return err
				}
			}
		}
	}
	for _, section := range sections {
		fmt.Fprintf(out, "%s: %d\n", section.name, len(section.rows))
		for _, row := range section.rows {
			fmt.Fprintf(out, "  %s\n", row)
		}
	}
	return nil
}
