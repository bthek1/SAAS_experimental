// Package refs keeps local copies of `catalog`'s types, and every way they change (#13).
// The rules, as in instances_NET's Refs/RefService.cs (and Django's refs.py before it):
//
//   - An event carries a type's full state and version. Applying one twice changes nothing,
//     and an older one is ignored, so duplicates and reordering are harmless.
//   - Retiring a copy deletes it and leaves a tombstone, which stops a late event from
//     bringing it back. A copy that instances use cannot be deleted.
//   - A synchronous answer from `catalog` is authoritative: the type exists right now. That
//     clears a tombstone, which is how a delete that failed after its retire heals.
package refs

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	"instances/internal/cache"
	"instances/internal/httpx"
	"instances/internal/peers"
)

// Results of an event.
const (
	Applied = "applied"
	Ignored = "ignored"
)

// ErrInUse is a copy that instances still use, so it cannot be retired.
var ErrInUse = errors.New("in use")

var readThroughs = promauto.NewCounterVec(prometheus.CounterOpts{
	Name: "app_ref_read_through_total",
	Help: "Copies fetched from catalog because they had not arrived, by result.",
}, []string{"result"})

// Service changes the copies.
type Service struct {
	Pool    *pgxpool.Pool
	Cache   *cache.Cache
	Catalog peers.Catalog
}

// Work is one transaction, and the owners whose cached entries it invalidates. The
// generations are bumped only after the commit: before it, a reader could cache the old
// rows under the new generation. A rollback bumps nothing.
type Work struct {
	pgx.Tx
	bumps map[uuid.UUID]bool
}

// BumpAfterCommit records an owner whose entries the commit invalidates.
func (w *Work) BumpAfterCommit(owner uuid.UUID) { w.bumps[owner] = true }

// InTransaction runs fn in a transaction, then bumps the owners it named.
func InTransaction(ctx context.Context, pool *pgxpool.Pool, c *cache.Cache, fn func(*Work) error) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	work := &Work{Tx: tx, bumps: map[uuid.UUID]bool{}}
	if err := fn(work); err != nil {
		_ = tx.Rollback(ctx)
		return err
	}
	if err := tx.Commit(ctx); err != nil {
		return err
	}
	for owner := range work.bumps {
		c.BumpOwnerGeneration(ctx, owner)
	}
	return nil
}

// ApplyEvent applies one event from `catalog`. Safe to call any number of times.
func (s *Service) ApplyEvent(ctx context.Context, body json.RawMessage) (string, error) {
	e, err := parseEvent(body)
	if err != nil {
		return "", err
	}
	var result string
	err = InTransaction(ctx, s.Pool, s.Cache, func(w *Work) error {
		result, err = s.apply(ctx, e, w)
		return err
	})
	return result, err
}

func (s *Service) apply(ctx context.Context, e *event, w *Work) (string, error) {
	if e.Kind == "user" && (e.Action == "deactivated" || e.Action == "reactivated" || e.Action == "deleted") {
		owner, err := e.aggregateID()
		if err != nil {
			return "", err
		}
		version, err := e.version()
		if err != nil {
			return "", err
		}
		return applyUserEvent(ctx, w, e.Action, owner, version)
	}
	if !IsKnown(e.Kind) || (e.Action != "changed" && e.Action != "deleted") {
		return "", bad("unknown event type '%s'", e.Type)
	}
	id, err := e.aggregateID()
	if err != nil {
		return "", err
	}
	var retired bool
	if err := w.QueryRow(ctx, `SELECT EXISTS (SELECT 1 FROM questionnaires_retiredref WHERE kind = $1 AND ref_id = $2)`,
		e.Kind, id).Scan(&retired); err != nil {
		return "", err
	}
	if retired {
		return Ignored, nil
	}
	if e.Action == "deleted" {
		version, err := e.version()
		if err != nil {
			return "", err
		}
		return applyDeleted(ctx, w, e.Kind, id, version)
	}
	data, err := e.data()
	if err != nil {
		return "", err
	}
	t, err := parseTypeData(e.Kind, data)
	if err != nil {
		return "", err
	}
	// An owner's type event can arrive after the event that deleted the owner.
	var deleted bool
	if err := w.QueryRow(ctx, `SELECT EXISTS (SELECT 1 FROM questionnaires_blockedowner WHERE owner_id = $1 AND deleted)`,
		t.OwnerID).Scan(&deleted); err != nil {
		return "", err
	}
	if deleted {
		return Ignored, nil
	}
	version, err := e.version()
	if err != nil {
		return "", err
	}
	return upsert(ctx, w, e.Kind, id, version, t)
}

// StoreSnapshot stores an authoritative answer from `catalog`, clearing any tombstone.
func (s *Service) StoreSnapshot(ctx context.Context, snapshot json.RawMessage) error {
	e, err := parseEvent(snapshot)
	if err != nil {
		return err
	}
	if !IsKnown(e.Kind) {
		return bad("unknown snapshot type '%s'", e.Type)
	}
	id, err := e.aggregateID()
	if err != nil {
		return err
	}
	data, err := e.data()
	if err != nil {
		return err
	}
	t, err := parseTypeData(e.Kind, data)
	if err != nil {
		return err
	}
	version, err := e.version()
	if err != nil {
		return err
	}
	return InTransaction(ctx, s.Pool, s.Cache, func(w *Work) error {
		if _, err := w.Exec(ctx, `DELETE FROM questionnaires_retiredref WHERE kind = $1 AND ref_id = $2`, e.Kind, id); err != nil {
			return err
		}
		_, err := upsert(ctx, w, e.Kind, id, version, t)
		return err
	})
}

func upsert(ctx context.Context, w *Work, kind string, id uuid.UUID, version int64, t *typeData) (string, error) {
	// Insert, or lock the row that is there: two events for one type serialize here.
	var tag interface{ RowsAffected() int64 }
	var err error
	if kind == QuestionnaireType {
		tag, err = w.Exec(ctx, `INSERT INTO questionnaires_questionnairetyperef
			    (id, title, created_at, updated_at, version, owner_id, questionnaire_json)
			VALUES ($1, $2, $3, $4, $5, $6, $7::text::jsonb)
			ON CONFLICT (id) DO NOTHING`, id, t.Title, t.CreatedAt, t.UpdatedAt, version, t.OwnerID, t.QuestionnaireJSON)
	} else {
		tag, err = w.Exec(ctx, `INSERT INTO questionnaires_batterytyperef
			    (id, title, created_at, updated_at, version, owner_id, description)
			VALUES ($1, $2, $3, $4, $5, $6, $7)
			ON CONFLICT (id) DO NOTHING`, id, t.Title, t.CreatedAt, t.UpdatedAt, version, t.OwnerID, t.Description)
	}
	if err != nil {
		return "", err
	}
	if tag.RowsAffected() != 1 {
		var current int64
		if err := w.QueryRow(ctx, `SELECT version FROM `+table(kind)+` WHERE id = $1 FOR UPDATE`, id).Scan(&current); err != nil {
			return "", err
		}
		if current >= version {
			return Ignored, nil
		}
		if kind == QuestionnaireType {
			_, err = w.Exec(ctx, `UPDATE questionnaires_questionnairetyperef
				SET title = $2, created_at = $3, updated_at = $4, version = $5, owner_id = $6,
				    questionnaire_json = $7::text::jsonb
				WHERE id = $1`, id, t.Title, t.CreatedAt, t.UpdatedAt, version, t.OwnerID, t.QuestionnaireJSON)
		} else {
			_, err = w.Exec(ctx, `UPDATE questionnaires_batterytyperef
				SET title = $2, created_at = $3, updated_at = $4, version = $5, owner_id = $6, description = $7
				WHERE id = $1`, id, t.Title, t.CreatedAt, t.UpdatedAt, version, t.OwnerID, t.Description)
		}
		if err != nil {
			return "", err
		}
	}
	if kind == BatteryType {
		if _, err := w.Exec(ctx, `DELETE FROM questionnaires_batterytyperefslot WHERE battery_type_id = $1`, id); err != nil {
			return "", err
		}
		if len(t.Items) > 0 {
			types := make([]uuid.UUID, len(t.Items))
			orders := make([]int32, len(t.Items))
			for i, item := range t.Items {
				types[i], orders[i] = item.QuestionnaireTypeID, item.Order
			}
			if _, err := w.Exec(ctx, `INSERT INTO questionnaires_batterytyperefslot (battery_type_id, questionnaire_type_id, "order")
				SELECT $1, t, o FROM unnest($2::uuid[], $3::int[]) AS s(t, o)`, id, types, orders); err != nil {
				return "", err
			}
		}
	}
	// Dashboards show titles, and score labels come from the definition.
	w.BumpAfterCommit(t.OwnerID)
	return Applied, nil
}

func table(kind string) string {
	if kind == QuestionnaireType {
		return "questionnaires_questionnairetyperef"
	}
	return "questionnaires_batterytyperef"
}

type copyRow struct {
	Owner   uuid.UUID
	Version int64
}

func current(ctx context.Context, w *Work, kind string, id uuid.UUID, forUpdate bool) (*copyRow, error) {
	sql := `SELECT owner_id, version FROM ` + table(kind) + ` WHERE id = $1`
	if forUpdate {
		sql += ` FOR UPDATE`
	}
	var row copyRow
	err := w.QueryRow(ctx, sql, id).Scan(&row.Owner, &row.Version)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	return &row, err
}

func inUse(ctx context.Context, q interface {
	QueryRow(context.Context, string, ...any) pgx.Row
}, kind string, id uuid.UUID) (bool, error) {
	sql := `SELECT EXISTS (SELECT 1 FROM questionnaires_questionnaire WHERE questionnaire_type_id = $1)`
	if kind == BatteryType {
		sql = `SELECT EXISTS (SELECT 1 FROM questionnaires_battery WHERE battery_type_id = $1)`
	}
	var used bool
	err := q.QueryRow(ctx, sql, id).Scan(&used)
	return used, err
}

func deleteCopy(ctx context.Context, w *Work, kind string, id uuid.UUID) error {
	if kind == BatteryType {
		if _, err := w.Exec(ctx, `DELETE FROM questionnaires_batterytyperefslot WHERE battery_type_id = $1`, id); err != nil {
			return err
		}
	}
	_, err := w.Exec(ctx, `DELETE FROM `+table(kind)+` WHERE id = $1`, id)
	return err
}

func tombstone(ctx context.Context, w *Work, kind string, id uuid.UUID) error {
	_, err := w.Exec(ctx, `INSERT INTO questionnaires_retiredref (kind, ref_id, retired_at) VALUES ($1, $2, $3)
		ON CONFLICT (kind, ref_id) DO NOTHING`, kind, id, httpx.Now())
	return err
}

func applyDeleted(ctx context.Context, w *Work, kind string, id uuid.UUID, version int64) (string, error) {
	existing, err := current(ctx, w, kind, id, false)
	if err != nil {
		return "", err
	}
	if existing != nil {
		if existing.Version >= version {
			return Ignored, nil
		}
		used, err := inUse(ctx, w, kind, id)
		if err != nil {
			return "", err
		}
		if used {
			// An instance was created between the retire and the delete, through a
			// read-through. Its answers stay readable; reconcile-refs reports it.
			slog.Warn("deleted copy still has instances", "kind", kind, "id", id)
			return Ignored, nil
		}
		if err := deleteCopy(ctx, w, kind, id); err != nil {
			return "", err
		}
		w.BumpAfterCommit(existing.Owner)
	}
	if err := tombstone(ctx, w, kind, id); err != nil {
		return "", err
	}
	return Applied, nil
}

func applyUserEvent(ctx context.Context, w *Work, action string, owner uuid.UUID, version int64) (string, error) {
	var deleted bool
	var stored int64
	err := w.QueryRow(ctx, `SELECT deleted, version FROM questionnaires_blockedowner WHERE owner_id = $1 FOR UPDATE`,
		owner).Scan(&deleted, &stored)
	if err == nil && (deleted || stored >= version) {
		return Ignored, nil
	}
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		return "", err
	}
	blocked, isDeleted := action != "reactivated", action == "deleted"
	if _, err := w.Exec(ctx, `INSERT INTO questionnaires_blockedowner (owner_id, blocked, deleted, version)
		VALUES ($1, $2, $3, $4)
		ON CONFLICT (owner_id) DO UPDATE
		SET blocked = EXCLUDED.blocked, deleted = EXCLUDED.deleted, version = EXCLUDED.version`,
		owner, blocked, isDeleted, version); err != nil {
		return "", err
	}
	if isDeleted {
		// In this order: the copies are RESTRICTed by what is made from them.
		for _, sql := range []string{
			`DELETE FROM questionnaires_questionnaire WHERE owner_id = $1`,
			`DELETE FROM questionnaires_battery WHERE owner_id = $1`,
			`DELETE FROM questionnaires_questionnairetyperef WHERE owner_id = $1`,
			`DELETE FROM questionnaires_batterytyperefslot s USING questionnaires_batterytyperef t
			 WHERE t.id = s.battery_type_id AND t.owner_id = $1`,
			`DELETE FROM questionnaires_batterytyperef WHERE owner_id = $1`,
		} {
			if _, err := w.Exec(ctx, sql, owner); err != nil {
				return "", err
			}
		}
	}
	w.BumpAfterCommit(owner)
	return Applied, nil
}

// Retire deletes a copy before its source goes. ErrInUse if instances use it.
func (s *Service) Retire(ctx context.Context, kind string, id uuid.UUID) error {
	return InTransaction(ctx, s.Pool, s.Cache, func(w *Work) error {
		existing, err := current(ctx, w, kind, id, true)
		if err != nil {
			return err
		}
		if existing != nil {
			used, err := inUse(ctx, w, kind, id)
			if err != nil {
				return err
			}
			if used {
				return ErrInUse
			}
			if err := deleteCopy(ctx, w, kind, id); err != nil {
				return err
			}
			w.BumpAfterCommit(existing.Owner)
		}
		return tombstone(ctx, w, kind, id)
	})
}

// ReadThrough fetches the copy from `catalog`: false if `catalog` has no such type.
func (s *Service) ReadThrough(ctx context.Context, kind string, id uuid.UUID) (bool, error) {
	snapshot, err := s.Catalog.Fetch(ctx, kind, id.String())
	if err != nil {
		readThroughs.WithLabelValues("unavailable").Inc()
		return false, err
	}
	if snapshot == nil {
		readThroughs.WithLabelValues("missing").Inc()
		return false, nil
	}
	readThroughs.WithLabelValues("found").Inc()
	if err := s.StoreSnapshot(ctx, snapshot); err != nil {
		var badEvent *BadEvent
		if errors.As(err, &badEvent) {
			return false, &peers.Unavailable{Message: "catalog sent an unusable snapshot: " + badEvent.Message}
		}
		return false, err
	}
	return true, nil
}

// ReadThroughOr503 is ReadThrough with `catalog` unreachable as a 503.
func (s *Service) ReadThroughOr503(ctx context.Context, kind string, id uuid.UUID) (bool, error) {
	found, err := s.ReadThrough(ctx, kind, id)
	if peers.IsUnavailable(err) {
		return false, httpx.Detail(http.StatusServiceUnavailable, httpx.MsgUnavailable)
	}
	return found, err
}

// EnsureQuestionnaireTypes fetches any of these copies that have not arrived yet.
func (s *Service) EnsureQuestionnaireTypes(ctx context.Context, ids []uuid.UUID) error {
	if len(ids) == 0 {
		return nil
	}
	rows, err := s.Pool.Query(ctx, `SELECT id FROM questionnaires_questionnairetyperef WHERE id = ANY($1)`, ids)
	if err != nil {
		return err
	}
	present, err := pgx.CollectRows(rows, pgx.RowTo[uuid.UUID])
	if err != nil {
		return err
	}
	have := map[uuid.UUID]bool{}
	for _, id := range present {
		have[id] = true
	}
	for _, id := range ids {
		if have[id] {
			continue
		}
		have[id] = true
		found, err := s.ReadThroughOr503(ctx, QuestionnaireType, id)
		if err != nil {
			return err
		}
		if !found {
			// The slot list is out of date. The battery type's own event will fix it.
			return httpx.Detail(http.StatusServiceUnavailable, httpx.MsgUnavailable)
		}
	}
	return nil
}

// Resolve is an owned type's id from a request field, as Django's OwnedRefField: only the
// caller's own. A copy that has not arrived yet is fetched from `catalog` once; `catalog`
// being unreachable is a 503, since the id may well be valid, where a 400 would tell the
// owner their type is gone. A field error is recorded and gives nil.
func (s *Service) Resolve(ctx context.Context, value httpx.Value, kind, field string, owner uuid.UUID,
	errs *httpx.FieldErrors, required bool) (*uuid.UUID, error) {
	if value == nil {
		if required {
			errs.Add(field, httpx.MsgRequired)
		}
		return nil, nil
	}
	// DRF's relational fields take an empty string as null.
	if value.Kind() == "null" || (value.Kind() == "string" && value.String() == "") {
		errs.Add(field, httpx.MsgNotNull)
		return nil, nil
	}
	if value.Kind() != "string" {
		errs.Add(field, "Incorrect type. Expected pk value, received "+value.PythonType()+".")
		return nil, nil
	}
	return s.ResolveText(ctx, value.String(), kind, field, owner, errs)
}

// ResolveText is Resolve for a query parameter's text.
func (s *Service) ResolveText(ctx context.Context, text, kind, field string, owner uuid.UUID,
	errs *httpx.FieldErrors) (*uuid.UUID, error) {
	if text == "" {
		errs.Add(field, httpx.MsgNotNull)
		return nil, nil
	}
	id, ok := pythonUUID(text)
	if !ok {
		errs.Add(field, httpx.MsgNotAValidUUID(text))
		return nil, nil
	}
	found, err := s.ownerOf(ctx, kind, id)
	if err != nil {
		return nil, err
	}
	if found != nil && *found == owner {
		return &id, nil
	}
	// Another owner's copy: nothing `catalog` says would change the answer.
	if found == nil {
		fetched, err := s.ReadThroughOr503(ctx, kind, id)
		if err != nil {
			return nil, err
		}
		if fetched {
			if found, err = s.ownerOf(ctx, kind, id); err != nil {
				return nil, err
			}
			if found != nil && *found == owner {
				return &id, nil
			}
		}
	}
	errs.Add(field, httpx.MsgDoesNotExist(text))
	return nil, nil
}

// pythonUUID takes the spellings both Python's uuid.UUID and .NET's Guid.TryParse read:
// 32 hex digits, with dashes, or in braces.
func pythonUUID(text string) (uuid.UUID, bool) {
	if len(text) == 38 && text[0] == '{' && text[37] == '}' {
		text = text[1:37]
	}
	if len(text) != 32 && len(text) != 36 {
		return uuid.UUID{}, false
	}
	id, err := uuid.Parse(text)
	return id, err == nil
}

func (s *Service) ownerOf(ctx context.Context, kind string, id uuid.UUID) (*uuid.UUID, error) {
	var owner uuid.UUID
	err := s.Pool.QueryRow(ctx, `SELECT owner_id FROM `+table(kind)+` WHERE id = $1`, id).Scan(&owner)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &owner, nil
}

// InUse is true while instances use the copy.
func (s *Service) InUse(ctx context.Context, kind string, id uuid.UUID) (bool, error) {
	return inUse(ctx, s.Pool, kind, id)
}
