package api

import (
	"fmt"
	"net/http"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/google/uuid"

	"instances/internal/cache"
	"instances/internal/dashboard"
	"instances/internal/httpx"
	"instances/internal/pdf"
	"instances/internal/refs"
	"instances/internal/server"
)

// The dashboards are cached per owner (#11, #19). Auth and validation run first, so a
// blocked owner or a foreign type is refused on a hit too. New questionnaires and
// submissions reach a cached dashboard within dashboardCacheFor: invalidating on them
// would leave little to hit under write-heavy traffic.
const dashboardCacheFor = 30 * time.Second

var dayChoices = map[string]int{"7": 7, "30": 30, "90": 90}

type dashboardParams struct {
	days     *int
	typeID   *uuid.UUID
	zone     *time.Location
	zoneName string
}

func (h *Handlers) dashboardParams(r *server.Request, typeRequired bool) (*dashboardParams, error) {
	var errs httpx.FieldErrors
	p := &dashboardParams{zone: time.UTC, zoneName: "UTC"}
	if text := httpx.QueryValue(r.R, "days"); text != nil {
		if choice, ok := dayChoices[*text]; ok {
			p.days = &choice
		} else {
			errs.Add("days", fmt.Sprintf("\"%s\" is not a valid choice.", *text))
		}
	}
	if text := httpx.QueryValue(r.R, "questionnaireType"); text != nil {
		id, err := h.Refs.ResolveText(r.R.Context(), *text, refs.QuestionnaireType, "questionnaireType", r.Owner, &errs)
		if err != nil {
			return nil, err
		}
		p.typeID = id
	} else if typeRequired {
		errs.Add("questionnaireType", httpx.MsgRequired)
	}
	if raw := httpx.QueryValue(r.R, "tz"); raw != nil {
		name := strings.TrimSpace(*raw)
		switch {
		case name == "":
			errs.Add("tz", httpx.MsgNotBlank)
		case utf8.RuneCountInString(name) > dashboard.MaxZoneLength:
			errs.Add("tz", fmt.Sprintf("Ensure this field has no more than %d characters.", dashboard.MaxZoneLength))
		default:
			if zone := dashboard.FindZone(name); zone != nil {
				p.zone, p.zoneName = zone, name
			} else {
				errs.Add("tz", "Unknown time zone.")
			}
		}
	}
	return p, errs.Err()
}

// cacheParams is the key's parameters, as .NET names them.
type cacheParams struct {
	Days              *int       `json:"days"`
	QuestionnaireType *uuid.UUID `json:"questionnaireType"`
	Tz                string     `json:"tz"`
}

// Summary is `/api/dashboard/`.
func (h *Handlers) Summary(r *server.Request) error {
	p, err := h.dashboardParams(r, false)
	if err != nil {
		return err
	}
	ctx := r.R.Context()
	body, err := h.Cache.Cached(ctx, "dashboard", r.Owner, cacheParams{p.days, p.typeID, p.zoneName}, dashboardCacheFor,
		func() ([]byte, error) {
			summary, err := h.Dashboard.Summary(ctx, r.Owner, p.days, p.typeID, p.zone, p.zoneName)
			if err != nil {
				return nil, err
			}
			return httpx.Encode(summary), nil
		}, cache.Options{})
	if err != nil {
		return err
	}
	httpx.WriteBytes(r.W, http.StatusOK, body)
	return nil
}

// Scores is `/api/dashboard/scores/`.
func (h *Handlers) Scores(r *server.Request) error {
	p, err := h.dashboardParams(r, true)
	if err != nil {
		return err
	}
	ctx := r.R.Context()
	body, err := h.Cache.Cached(ctx, "dashboard-scores", r.Owner, cacheParams{p.days, p.typeID, p.zoneName},
		dashboardCacheFor, func() ([]byte, error) {
			scores, err := h.Dashboard.Scores(ctx, r.Owner, *p.typeID, p.days, p.zone)
			if err != nil {
				return nil, err
			}
			return httpx.Encode(scores), nil
		}, cache.Options{Version: 2})
	if err != nil {
		return err
	}
	httpx.WriteBytes(r.W, http.StatusOK, body)
	return nil
}

const (
	pdfCacheFor      = 24 * time.Hour
	pdfCacheMaxBytes = 2 * 1024 * 1024
	// Bump when internal/pdf changes what it draws.
	pdfCacheVersion = 1
)

var unsafeFilename = regexp.MustCompile(`[^A-Za-z0-9_-]+`)

// PDF is a submitted response as a PDF download.
func (h *Handlers) PDF(r *server.Request) error {
	ctx := r.R.Context()
	q, err := h.findOwned(ctx, r.Owner, r.Param("id"))
	if err != nil {
		return err
	}
	if q.SubmittedAt == nil {
		return httpx.Detail(http.StatusBadRequest, "This questionnaire has not been submitted.")
	}
	stem := strings.Trim(unsafeFilename.ReplaceAllString(q.TypeTitle, "-"), "-")
	if len(stem) > 60 {
		stem = stem[:60]
	}
	if stem == "" {
		stem = "response"
	}
	filename := fmt.Sprintf("%s-%s.pdf", stem, time.Now().UTC().Format("2006-01-02"))
	// A submitted response never changes. The PDF also reads its name and the type's
	// title, so these timestamps identify the content: no generation needed.
	params := struct {
		ID            uuid.UUID `json:"id"`
		UpdatedAt     string    `json:"updatedAt"`
		TypeUpdatedAt string    `json:"typeUpdatedAt"`
	}{q.ID, httpx.Format(q.UpdatedAt), httpx.Format(q.TypeUpdated)}
	content, err := h.Cache.Cached(ctx, "pdf", r.Owner, params, pdfCacheFor, func() ([]byte, error) {
		return pdf.Render(pdf.Response{TypeTitle: q.TypeTitle, Name: q.Name, SubmittedAt: *q.SubmittedAt,
			Snapshot: q.Snapshot, Answers: q.Answers, MetricsRaw: q.Metrics})
	}, cache.Options{Version: pdfCacheVersion, NoGeneration: true,
		StoreIf: func(b []byte) bool { return len(b) <= pdfCacheMaxBytes }})
	if err != nil {
		return err
	}
	header := r.W.Header()
	header.Set("Content-Type", "application/pdf")
	header.Set("Content-Disposition", fmt.Sprintf(`attachment; filename="%s"`, filename))
	header.Set("Content-Length", fmt.Sprint(len(content)))
	r.W.WriteHeader(http.StatusOK)
	_, _ = r.W.Write(content)
	return nil
}
