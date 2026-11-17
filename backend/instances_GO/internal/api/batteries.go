package api

import (
	"context"
	"net/http"
	"sort"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"instances/internal/httpx"
	"instances/internal/refs"
	"instances/internal/server"
)

// Batteries: one questionnaire per slot of the battery type, in slot order. A battery is
// created and deleted, never edited.

const batteryTypeField = "batteryTypeId"

type batteryRow struct {
	ID, TypeID, OwnerID, ShareToken uuid.UUID
	TypeTitle, Name                 string
	CreatedAt, UpdatedAt            time.Time
	slots                           []slotRow
}

type slotRow struct {
	ID, ShareToken uuid.UUID
	Order          *int32
	TypeTitle      string
	SubmittedAt    *time.Time
}

func (b *batteryRow) isComplete() bool {
	if len(b.slots) == 0 {
		return false
	}
	for _, s := range b.slots {
		if s.SubmittedAt == nil {
			return false
		}
	}
	return true
}

func (b *batteryRow) out() batteryOut {
	slots := make([]slotOut, len(b.slots))
	for i, s := range b.slots {
		slots[i] = slotOut{s.Order, s.ID, s.ShareToken, s.TypeTitle, optionalTime(s.SubmittedAt)}
	}
	return batteryOut{
		ID: b.ID, BatteryTypeID: b.TypeID, BatteryTypeName: b.TypeTitle, Name: b.Name, ShareToken: b.ShareToken,
		Questionnaires: slots, IsComplete: b.isComplete(),
		CreatedAt: httpx.Time{Time: b.CreatedAt}, UpdatedAt: httpx.Time{Time: b.UpdatedAt},
	}
}

func (b *batteryRow) public() publicBatteryOut {
	slots := make([]publicSlotOut, len(b.slots))
	for i, s := range b.slots {
		slots[i] = publicSlotOut{s.Order, s.ShareToken, s.TypeTitle, optionalTime(s.SubmittedAt)}
	}
	return publicBatteryOut{ID: b.ID, Name: b.Name, BatteryTypeName: b.TypeTitle, Questionnaires: slots,
		IsComplete: b.isComplete()}
}

// batteries runs a select of batteries with their types, then one query for every slot
// of them: a fixed number of queries whatever the rows.
func (h *Handlers) batteries(ctx context.Context, sql string, args ...any) ([]*batteryRow, error) {
	rows, err := h.Pool.Query(ctx, `SELECT b.id, b.battery_type_id, b.owner_id, b.share_token, t.title, b.name,
		    b.created_at, b.updated_at
		FROM questionnaires_battery b JOIN questionnaires_batterytyperef t ON t.id = b.battery_type_id `+sql, args...)
	if err != nil {
		return nil, err
	}
	found, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (*batteryRow, error) {
		b := &batteryRow{}
		err := row.Scan(&b.ID, &b.TypeID, &b.OwnerID, &b.ShareToken, &b.TypeTitle, &b.Name, &b.CreatedAt, &b.UpdatedAt)
		return b, err
	})
	if err != nil || len(found) == 0 {
		return found, err
	}
	ids := make([]uuid.UUID, len(found))
	byID := map[uuid.UUID]*batteryRow{}
	for i, b := range found {
		ids[i] = b.ID
		byID[b.ID] = b
	}
	slots, err := h.Pool.Query(ctx, `SELECT q.battery_id, q.id, q.share_token, q.battery_order, t.title, q.submitted_at
		FROM questionnaires_questionnaire q JOIN questionnaires_questionnairetyperef t ON t.id = q.questionnaire_type_id
		WHERE q.battery_id = ANY($1)`, ids)
	if err != nil {
		return nil, err
	}
	defer slots.Close()
	for slots.Next() {
		var battery uuid.UUID
		var s slotRow
		if err := slots.Scan(&battery, &s.ID, &s.ShareToken, &s.Order, &s.TypeTitle, &s.SubmittedAt); err != nil {
			return nil, err
		}
		byID[battery].slots = append(byID[battery].slots, s)
	}
	if err := slots.Err(); err != nil {
		return nil, err
	}
	for _, b := range found {
		// Slot order; a slot without one (never made so) last.
		sort.SliceStable(b.slots, func(i, j int) bool {
			a, c := b.slots[i].Order, b.slots[j].Order
			if a == nil || c == nil {
				return a != nil
			}
			return *a < *c
		})
	}
	return found, nil
}

// ListBatteries is the owner's batteries, newest first.
func (h *Handlers) ListBatteries(r *server.Request) error {
	ctx := r.R.Context()
	page, err := httpx.PaginationFrom(r.R)
	if err != nil {
		return err
	}
	var count int
	if err := h.Pool.QueryRow(ctx, `SELECT count(*) FROM questionnaires_battery WHERE owner_id = $1`, r.Owner).
		Scan(&count); err != nil {
		return err
	}
	rows, err := h.batteries(ctx, `WHERE b.owner_id = $1 ORDER BY b.created_at DESC, b.id DESC LIMIT $2 OFFSET $3`,
		r.Owner, page.Size, page.Skip())
	if err != nil {
		return err
	}
	results := make([]batteryOut, len(rows))
	for i, row := range rows {
		results[i] = row.out()
	}
	body, err := httpx.BuildPage(r.R, page, count, results)
	if err != nil {
		return err
	}
	httpx.WriteJSON(r.W, http.StatusOK, body)
	return nil
}

// CreateBattery makes a battery and a questionnaire for each slot of its type.
func (h *Handlers) CreateBattery(r *server.Request) error {
	ctx := r.R.Context()
	body, err := httpx.ReadObject(r.R)
	if err != nil {
		return err
	}
	var errs httpx.FieldErrors
	typeID, err := h.Refs.Resolve(ctx, body.Field(batteryTypeField), refs.BatteryType, batteryTypeField, r.Owner, &errs, true)
	if err != nil {
		return err
	}
	name, _ := httpx.Text(body.Field("name"), "name", &errs, 255)
	if err := errs.Err(); err != nil {
		return err
	}
	var typeOwner uuid.UUID
	if err := h.Pool.QueryRow(ctx, `SELECT owner_id FROM questionnaires_batterytyperef WHERE id = $1`, *typeID).
		Scan(&typeOwner); err != nil {
		return err
	}
	rows, err := h.Pool.Query(ctx, `SELECT questionnaire_type_id, "order" FROM questionnaires_batterytyperefslot
		WHERE battery_type_id = $1 ORDER BY "order"`, *typeID)
	if err != nil {
		return err
	}
	type slot struct {
		typeID uuid.UUID
		order  int32
	}
	slots, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (slot, error) {
		var s slot
		return s, row.Scan(&s.typeID, &s.order)
	})
	if err != nil {
		return err
	}
	// Outside the transaction: this can call `catalog`, and each slot needs a copy.
	types := make([]uuid.UUID, len(slots))
	for i, s := range slots {
		types[i] = s.typeID
	}
	if err := h.Refs.EnsureQuestionnaireTypes(ctx, types); err != nil {
		return err
	}

	now := httpx.Now()
	id := uuid.New()
	// The battery and its slots, or nothing.
	err = pgx.BeginFunc(ctx, h.Pool, func(tx pgx.Tx) error {
		if _, err := tx.Exec(ctx, `INSERT INTO questionnaires_battery
			    (id, created_at, updated_at, owner_id, name, share_token, battery_type_id)
			VALUES ($1, $2, $2, $3, $4, $5, $6)`, id, now, typeOwner, name, uuid.New(), *typeID); err != nil {
			return err
		}
		if len(slots) == 0 {
			return nil
		}
		ids, tokens, orders := make([]uuid.UUID, len(slots)), make([]uuid.UUID, len(slots)), make([]int32, len(slots))
		for i, s := range slots {
			ids[i], tokens[i], orders[i] = uuid.New(), uuid.New(), s.order
		}
		_, err := tx.Exec(ctx, `INSERT INTO questionnaires_questionnaire
			    (id, created_at, updated_at, owner_id, battery_order, name, share_token, answers_json,
			     questionnaire_json_snapshot, metrics_json, submitted_at, battery_id, questionnaire_type_id)
			SELECT i, $1, $1, $2, o, '', s, '{}', '{}', '{}', NULL, $3, t
			FROM unnest($4::uuid[], $5::uuid[], $6::int[], $7::uuid[]) AS x(i, s, o, t)`,
			now, typeOwner, id, ids, tokens, orders, types)
		return err
	})
	if err != nil {
		return err
	}
	created, err := h.batteries(ctx, `WHERE b.id = $1`, id)
	if err != nil {
		return err
	}
	httpx.WriteJSON(r.W, http.StatusCreated, created[0].out())
	return nil
}

// GetBattery is one of the owner's batteries.
func (h *Handlers) GetBattery(r *server.Request) error {
	id, ok := server.ParseGUID(r.Param("id"))
	if !ok {
		return httpx.NotFound()
	}
	rows, err := h.batteries(r.R.Context(), `WHERE b.id = $1 AND b.owner_id = $2`, id, r.Owner)
	if err != nil {
		return err
	}
	if len(rows) == 0 {
		return httpx.NotFound()
	}
	httpx.WriteJSON(r.W, http.StatusOK, rows[0].out())
	return nil
}

// DeleteBattery deletes a battery. Its questionnaires stay, without a battery (Django's
// SET_NULL).
func (h *Handlers) DeleteBattery(r *server.Request) error {
	ctx := r.R.Context()
	id, ok := server.ParseGUID(r.Param("id"))
	if !ok {
		return httpx.NotFound()
	}
	var exists bool
	if err := h.Pool.QueryRow(ctx, `SELECT EXISTS (SELECT 1 FROM questionnaires_battery WHERE id = $1 AND owner_id = $2)`,
		id, r.Owner).Scan(&exists); err != nil {
		return err
	}
	if !exists {
		return httpx.NotFound()
	}
	err := refs.InTransaction(ctx, h.Pool, h.Cache, func(w *refs.Work) error {
		if _, err := w.Exec(ctx, `UPDATE questionnaires_questionnaire SET battery_id = NULL WHERE battery_id = $1`, id); err != nil {
			return err
		}
		if _, err := w.Exec(ctx, `DELETE FROM questionnaires_battery WHERE id = $1`, id); err != nil {
			return err
		}
		w.BumpAfterCommit(r.Owner)
		return nil
	})
	if err != nil {
		return err
	}
	httpx.WriteJSON(r.W, http.StatusNoContent, nil)
	return nil
}

// ReadBatteryByToken is what a respondent opens: the battery and its share links.
func (h *Handlers) ReadBatteryByToken(r *server.Request) error {
	token, ok := server.ParseGUID(r.Param("shareToken"))
	if !ok {
		return httpx.NotFound()
	}
	rows, err := h.batteries(r.R.Context(), `WHERE b.share_token = $1`, token)
	if err != nil {
		return err
	}
	if len(rows) == 0 {
		return httpx.NotFound()
	}
	httpx.WriteJSON(r.W, http.StatusOK, rows[0].public())
	return nil
}
