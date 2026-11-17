// Package api is the endpoints, as instances_NET's controllers serve them: the owner's
// questionnaires and batteries, the share-link endpoints a respondent uses, the
// dashboards, and what `catalog` may ask on `/internal/`.
package api

import (
	"context"
	"encoding/json"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"instances/internal/cache"
	"instances/internal/config"
	"instances/internal/dashboard"
	"instances/internal/httpx"
	"instances/internal/refs"
)

// Handlers serve the endpoints.
type Handlers struct {
	Settings  *config.Settings
	Pool      *pgxpool.Pool
	Refs      *refs.Service
	Cache     *cache.Cache
	Dashboard *dashboard.Service
}

// Response bodies, field for field as Django's serializers wrote them.

type typeOut struct {
	ID                uuid.UUID       `json:"id"`
	Title             string          `json:"title"`
	QuestionnaireJSON json.RawMessage `json:"questionnaireJson"`
	CreatedAt         httpx.Time      `json:"createdAt"`
	UpdatedAt         httpx.Time      `json:"updatedAt"`
}

type questionnaireOut struct {
	ID                        uuid.UUID       `json:"id"`
	QuestionnaireTypeID       uuid.UUID       `json:"questionnaireTypeId"`
	QuestionnaireType         typeOut         `json:"questionnaireType"`
	BatteryID                 *uuid.UUID      `json:"batteryId"`
	BatteryOrder              *int32          `json:"batteryOrder"`
	Name                      string          `json:"name"`
	ShareToken                uuid.UUID       `json:"shareToken"`
	Answers                   json.RawMessage `json:"answers"`
	Metrics                   json.RawMessage `json:"metrics"`
	SubmittedAt               *httpx.Time     `json:"submittedAt"`
	QuestionnaireJSONSnapshot json.RawMessage `json:"questionnaireJsonSnapshot"`
	CreatedAt                 httpx.Time      `json:"createdAt"`
	UpdatedAt                 httpx.Time      `json:"updatedAt"`
}

// Share-link bodies: only what a respondent needs. No owner, no answers.
type publicQuestionnaireOut struct {
	ID                     uuid.UUID       `json:"id"`
	Name                   string          `json:"name"`
	QuestionnaireTypeTitle string          `json:"questionnaireTypeTitle"`
	QuestionnaireJSON      json.RawMessage `json:"questionnaireJson"`
	SubmittedAt            *httpx.Time     `json:"submittedAt"`
}

type slotOut struct {
	Order                 *int32      `json:"order"`
	QuestionnaireID       uuid.UUID   `json:"questionnaireId"`
	ShareToken            uuid.UUID   `json:"shareToken"`
	QuestionnaireTypeName string      `json:"questionnaireTypeName"`
	SubmittedAt           *httpx.Time `json:"submittedAt"`
}

type batteryOut struct {
	ID              uuid.UUID  `json:"id"`
	BatteryTypeID   uuid.UUID  `json:"batteryTypeId"`
	BatteryTypeName string     `json:"batteryTypeName"`
	Name            string     `json:"name"`
	ShareToken      uuid.UUID  `json:"shareToken"`
	Questionnaires  []slotOut  `json:"questionnaires"`
	IsComplete      bool       `json:"isComplete"`
	CreatedAt       httpx.Time `json:"createdAt"`
	UpdatedAt       httpx.Time `json:"updatedAt"`
}

type publicSlotOut struct {
	Order                 *int32      `json:"order"`
	ShareToken            uuid.UUID   `json:"shareToken"`
	QuestionnaireTypeName string      `json:"questionnaireTypeName"`
	SubmittedAt           *httpx.Time `json:"submittedAt"`
}

type publicBatteryOut struct {
	ID              uuid.UUID       `json:"id"`
	Name            string          `json:"name"`
	BatteryTypeName string          `json:"batteryTypeName"`
	Questionnaires  []publicSlotOut `json:"questionnaires"`
	IsComplete      bool            `json:"isComplete"`
}

func optionalTime(t *time.Time) *httpx.Time {
	if t == nil {
		return nil
	}
	return &httpx.Time{Time: *t}
}

// questionnaireRow is a questionnaire with its type, as the queries below select it.
type questionnaireRow struct {
	ID, TypeID, OwnerID, ShareToken uuid.UUID
	TypeTitle, TypeJSON             string
	TypeCreated, TypeUpdated        time.Time
	BatteryID                       *uuid.UUID
	BatteryOrder                    *int32
	Name                            string
	Answers, Metrics, Snapshot      string
	SubmittedAt                     *time.Time
	CreatedAt, UpdatedAt            time.Time
}

const questionnaireColumns = `q.id, q.questionnaire_type_id, q.owner_id, q.share_token, t.title, t.questionnaire_json::text,
	t.created_at, t.updated_at, q.battery_id, q.battery_order, q.name, q.answers_json::text, q.metrics_json::text,
	q.questionnaire_json_snapshot::text, q.submitted_at, q.created_at, q.updated_at
	FROM questionnaires_questionnaire q
	JOIN questionnaires_questionnairetyperef t ON t.id = q.questionnaire_type_id`

func scanQuestionnaire(row pgx.CollectableRow) (questionnaireRow, error) {
	var q questionnaireRow
	err := row.Scan(&q.ID, &q.TypeID, &q.OwnerID, &q.ShareToken, &q.TypeTitle, &q.TypeJSON, &q.TypeCreated,
		&q.TypeUpdated, &q.BatteryID, &q.BatteryOrder, &q.Name, &q.Answers, &q.Metrics, &q.Snapshot,
		&q.SubmittedAt, &q.CreatedAt, &q.UpdatedAt)
	return q, err
}

func (q questionnaireRow) out() questionnaireOut {
	return questionnaireOut{
		ID:                  q.ID,
		QuestionnaireTypeID: q.TypeID,
		QuestionnaireType: typeOut{
			ID: q.TypeID, Title: q.TypeTitle, QuestionnaireJSON: json.RawMessage(q.TypeJSON),
			CreatedAt: httpx.Time{Time: q.TypeCreated}, UpdatedAt: httpx.Time{Time: q.TypeUpdated},
		},
		BatteryID:                 q.BatteryID,
		BatteryOrder:              q.BatteryOrder,
		Name:                      q.Name,
		ShareToken:                q.ShareToken,
		Answers:                   json.RawMessage(q.Answers),
		Metrics:                   json.RawMessage(q.Metrics),
		SubmittedAt:               optionalTime(q.SubmittedAt),
		QuestionnaireJSONSnapshot: json.RawMessage(q.Snapshot),
		CreatedAt:                 httpx.Time{Time: q.CreatedAt},
		UpdatedAt:                 httpx.Time{Time: q.UpdatedAt},
	}
}

// public is what a respondent sees: a submitted questionnaire shows the definition it
// was answered against.
func (q questionnaireRow) public() publicQuestionnaireOut {
	definition := q.TypeJSON
	if q.SubmittedAt != nil {
		definition = q.Snapshot
	}
	return publicQuestionnaireOut{
		ID: q.ID, Name: q.Name, QuestionnaireTypeTitle: q.TypeTitle,
		QuestionnaireJSON: json.RawMessage(definition), SubmittedAt: optionalTime(q.SubmittedAt),
	}
}

// queryQuestionnaires runs a select of questionnaireColumns.
func queryQuestionnaires(ctx context.Context, pool *pgxpool.Pool, sql string, args ...any) ([]questionnaireRow, error) {
	rows, err := pool.Query(ctx, `SELECT `+questionnaireColumns+` `+sql, args...)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, scanQuestionnaire)
}
