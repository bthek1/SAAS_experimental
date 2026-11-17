package api

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"

	"github.com/google/uuid"

	"instances/internal/httpx"
	"instances/internal/refs"
	"instances/internal/server"
)

const questionnaireTypeField = "questionnaireTypeId"

// ListQuestionnaires is the owner's questionnaires, newest first, filtered by type and
// by whether they were submitted.
func (h *Handlers) ListQuestionnaires(r *server.Request) error {
	ctx := r.R.Context()
	var errs httpx.FieldErrors
	where := "q.owner_id = $1"
	args := []any{r.Owner}
	if text := httpx.QueryValue(r.R, "questionnaireType"); text != nil {
		id, err := h.Refs.ResolveText(ctx, *text, refs.QuestionnaireType, "questionnaireType", r.Owner, &errs)
		if err != nil {
			return err
		}
		if id != nil {
			args = append(args, *id)
			where += " AND q.questionnaire_type_id = $" + strconv.Itoa(len(args))
		}
	}
	submitted := httpx.Boolean(httpx.QueryValue(r.R, "submitted"), "submitted", &errs)
	if err := errs.Err(); err != nil {
		return err
	}
	if submitted != nil {
		if *submitted {
			where += " AND q.submitted_at IS NOT NULL"
		} else {
			where += " AND q.submitted_at IS NULL"
		}
	}
	page, err := httpx.PaginationFrom(r.R)
	if err != nil {
		return err
	}
	var count int
	if err := h.Pool.QueryRow(ctx, `SELECT count(*) FROM questionnaires_questionnaire q WHERE `+where, args...).
		Scan(&count); err != nil {
		return err
	}
	// Newest first, then id: rows made in one request share a created_at, and a tie
	// would let a row repeat or vanish between pages.
	args = append(args, page.Size, page.Skip())
	rows, err := queryQuestionnaires(ctx, h.Pool, `WHERE `+where+` ORDER BY q.created_at DESC, q.id DESC
		LIMIT $`+strconv.Itoa(len(args)-1)+` OFFSET $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		return err
	}
	results := make([]questionnaireOut, len(rows))
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

// CreateQuestionnaire makes a questionnaire of one of the owner's types.
func (h *Handlers) CreateQuestionnaire(r *server.Request) error {
	ctx := r.R.Context()
	body, err := httpx.ReadObject(r.R)
	if err != nil {
		return err
	}
	var errs httpx.FieldErrors
	typeID, err := h.Refs.Resolve(ctx, body.Field(questionnaireTypeField), refs.QuestionnaireType,
		questionnaireTypeField, r.Owner, &errs, true)
	if err != nil {
		return err
	}
	name, _ := httpx.Text(body.Field("name"), "name", &errs, 255)
	if err := errs.Err(); err != nil {
		return err
	}
	now := httpx.Now()
	id := uuid.New()
	if _, err := h.Pool.Exec(ctx, `INSERT INTO questionnaires_questionnaire
		    (id, created_at, updated_at, owner_id, battery_order, name, share_token, answers_json,
		     questionnaire_json_snapshot, metrics_json, submitted_at, battery_id, questionnaire_type_id)
		VALUES ($1, $2, $2, $3, NULL, $4, $5, '{}', '{}', '{}', NULL, NULL, $6)`,
		id, now, r.Owner, name, uuid.New(), *typeID); err != nil {
		return err
	}
	return h.writeOwned(ctx, r, http.StatusCreated, id)
}

// GetQuestionnaire is one of the owner's questionnaires.
func (h *Handlers) GetQuestionnaire(r *server.Request) error {
	q, err := h.findOwned(r.R.Context(), r.Owner, r.Param("id"))
	if err != nil {
		return err
	}
	httpx.WriteJSON(r.W, http.StatusOK, q.out())
	return nil
}

// UpdateQuestionnaire renames a questionnaire. Its type cannot change.
func (h *Handlers) UpdateQuestionnaire(r *server.Request) error {
	ctx := r.R.Context()
	q, err := h.findOwned(ctx, r.Owner, r.Param("id"))
	if err != nil {
		return err
	}
	body, err := httpx.ReadObject(r.R)
	if err != nil {
		return err
	}
	var errs httpx.FieldErrors
	typeID, err := h.Refs.Resolve(ctx, body.Field(questionnaireTypeField), refs.QuestionnaireType,
		questionnaireTypeField, r.Owner, &errs, false)
	if err != nil {
		return err
	}
	if typeID != nil && *typeID != q.TypeID {
		errs.Add(questionnaireTypeField, "The type of an existing questionnaire cannot change.")
	}
	name, given := httpx.Text(body.Field("name"), "name", &errs, 255)
	if err := errs.Err(); err != nil {
		return err
	}
	if !given {
		name = q.Name
	}
	if _, err := h.Pool.Exec(ctx, `UPDATE questionnaires_questionnaire SET name = $2, updated_at = $3 WHERE id = $1`,
		q.ID, name, httpx.Now()); err != nil {
		return err
	}
	return h.writeOwned(ctx, r, http.StatusOK, q.ID)
}

// DeleteQuestionnaire deletes one of the owner's questionnaires.
func (h *Handlers) DeleteQuestionnaire(r *server.Request) error {
	ctx := r.R.Context()
	q, err := h.findOwned(ctx, r.Owner, r.Param("id"))
	if err != nil {
		return err
	}
	if _, err := h.Pool.Exec(ctx, `DELETE FROM questionnaires_questionnaire WHERE id = $1`, q.ID); err != nil {
		return err
	}
	// So a dashboard never links to a deleted row.
	h.Cache.BumpOwnerGeneration(ctx, r.Owner)
	httpx.WriteJSON(r.W, http.StatusNoContent, nil)
	return nil
}

func (h *Handlers) findOwned(ctx context.Context, owner uuid.UUID, text string) (*questionnaireRow, error) {
	id, ok := server.ParseGUID(text)
	if !ok {
		return nil, httpx.NotFound()
	}
	rows, err := queryQuestionnaires(ctx, h.Pool, `WHERE q.id = $1 AND q.owner_id = $2`, id, owner)
	if err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, httpx.NotFound()
	}
	return &rows[0], nil
}

func (h *Handlers) writeOwned(ctx context.Context, r *server.Request, status int, id uuid.UUID) error {
	q, err := h.findOwned(ctx, r.Owner, id.String())
	if err != nil {
		return err
	}
	httpx.WriteJSON(r.W, status, q.out())
	return nil
}

// ── Share links: no authentication at all, so a stale token cannot 401 ──────

func (h *Handlers) byToken(ctx context.Context, text string) (*questionnaireRow, error) {
	token, ok := server.ParseGUID(text)
	if !ok {
		return nil, httpx.NotFound()
	}
	rows, err := queryQuestionnaires(ctx, h.Pool, `WHERE q.share_token = $1`, token)
	if err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, httpx.NotFound()
	}
	return &rows[0], nil
}

// ReadQuestionnaireByToken is what a respondent opens.
func (h *Handlers) ReadQuestionnaireByToken(r *server.Request) error {
	q, err := h.byToken(r.R.Context(), r.Param("shareToken"))
	if err != nil {
		return err
	}
	httpx.WriteJSON(r.W, http.StatusOK, q.public())
	return nil
}

// SubmitByToken stores a respondent's answers, once.
func (h *Handlers) SubmitByToken(r *server.Request) error {
	ctx := r.R.Context()
	q, err := h.byToken(ctx, r.Param("shareToken"))
	if err != nil {
		return err
	}
	body, err := httpx.ReadObject(r.R)
	if err != nil {
		return err
	}
	var errs httpx.FieldErrors
	answers := httpx.JSONObject(body.Field("answers"), "answers", &errs, true)
	metrics := httpx.JSONObject(body.Field("metrics"), "metrics", &errs, false)
	if err := errs.Err(); err != nil {
		return err
	}
	if metrics == nil {
		metrics = json.RawMessage("{}")
	}
	// Once only, with the type's current definition as the snapshot, in one statement:
	// whichever of two submits commits first wins, and the other finds it submitted.
	now := httpx.Now()
	tag, err := h.Pool.Exec(ctx, `UPDATE questionnaires_questionnaire AS q
		SET answers_json = $2::text::jsonb, metrics_json = $3::text::jsonb,
		    questionnaire_json_snapshot = t.questionnaire_json, submitted_at = $4, updated_at = $4
		FROM questionnaires_questionnairetyperef AS t
		WHERE q.id = $1 AND t.id = q.questionnaire_type_id AND q.submitted_at IS NULL`,
		q.ID, string(answers), string(metrics), now)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return httpx.Detail(http.StatusConflict, "Already submitted.")
	}
	submitted, err := h.byToken(ctx, q.ShareToken.String())
	if err != nil {
		return err
	}
	httpx.WriteJSON(r.W, http.StatusOK, submitted.public())
	return nil
}
