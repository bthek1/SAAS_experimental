package dashboard

import (
	"context"
	"encoding/json"
	"slices"
	"sort"
	"strconv"
	"time"

	"github.com/google/uuid"

	"instances/internal/httpx"
	"instances/internal/ojson"
)

type ScoresOut struct {
	QuestionnaireTypeID uuid.UUID   `json:"questionnaireTypeId"`
	Metrics             []MetricOut `json:"metrics"`
}

type MetricOut struct {
	Name         string            `json:"name"`
	Label        string            `json:"label"`
	Kind         string            `json:"kind"`
	Count        int               `json:"count"`
	Points       []PointOut        `json:"points"`
	Mean         *float64          `json:"mean,omitempty"`
	Distribution []DistributionOut `json:"distribution,omitempty"`
}

type PointOut struct {
	QuestionnaireID uuid.UUID       `json:"questionnaireId"`
	Name            string          `json:"name"`
	SubmittedAt     httpx.Time      `json:"submittedAt"`
	Value           json.RawMessage `json:"value"`
}

type DistributionOut struct {
	Value json.RawMessage `json:"value"`
	Count int             `json:"count"`
}

// kindOf is a metric's kind: a boolean before a number, since Python's True is an int too.
func kindOf(v *ojson.Value) string {
	switch v.Kind {
	case "bool":
		return "boolean"
	case "number":
		return "numeric"
	case "string":
		return "categorical"
	}
	return ""
}

type totals struct {
	kind         string
	count        int
	sum          float64
	distribution map[string]*bucket
}

type bucket struct {
	value *ojson.Value
	count int
}

func (t *totals) add(v *ojson.Value) {
	t.count++
	if t.kind == "numeric" {
		t.sum += v.Float()
		return
	}
	// `str(value)`, which orders the distribution's ties.
	key := v.Str
	if v.Kind == "bool" {
		key = v.PyStr()
	}
	if b := t.distribution[key]; b != nil {
		b.count++
	} else {
		t.distribution[key] = &bucket{v, 1}
	}
}

// Scores is `/api/dashboard/scores/`: every stored metric of one type's submitted
// questionnaires, by metric. `count`, `mean` and `distribution` cover every row in the
// window; `points` holds only the latest ScorePointLimit. A metric's kind comes from its
// first value (number, text or boolean); later values of another kind are skipped. Labels
// and order follow the type's current `calculatedValues`, then any names only older
// snapshots had.
func (s *Service) Scores(ctx context.Context, owner, typeID uuid.UUID, days *int, zone *time.Location) (*ScoresOut, error) {
	values := map[string]any{"owner": owner, "type": typeID}
	where := `q.owner_id = :owner AND q.questionnaire_type_id = :type AND q.submitted_at IS NOT NULL`
	if start := WindowStart(days, nowIn(zone), zone); start != nil {
		values["from"] = start.UTC()
		where += ` AND q.submitted_at >= :from`
	}
	var definition string
	if err := s.Pool.QueryRow(ctx, `SELECT questionnaire_json::text FROM questionnaires_questionnairetyperef WHERE id = $1`,
		typeID).Scan(&definition); err != nil {
		return nil, err
	}
	labels, labelOrder := metricLabels(definition)

	metrics := map[string]*totals{}
	var order []string
	rows, err := s.query(ctx, `SELECT q.metrics_json::text FROM questionnaires_questionnaire q WHERE `+where+
		` ORDER BY q.submitted_at, q.id`, values)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var stored string
		if err := rows.Scan(&stored); err != nil {
			rows.Close()
			return nil, err
		}
		document, err := ojson.Parse([]byte(stored))
		if err != nil || document.Kind != "object" {
			continue
		}
		for _, name := range document.Keys {
			value := document.Get(name)
			kind := kindOf(value)
			if kind == "" {
				continue
			}
			t := metrics[name]
			if t == nil {
				t = &totals{kind: kind, distribution: map[string]*bucket{}}
				metrics[name] = t
				order = append(order, name)
			}
			if kind == t.kind {
				t.add(value)
			}
		}
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	const name = `CASE WHEN q.name <> '' THEN q.name ELSE coalesce(b.name, '') END`
	rows, err = s.query(ctx, `SELECT q.id, `+name+`, q.submitted_at, q.metrics_json::text
		FROM questionnaires_questionnaire q LEFT JOIN questionnaires_battery b ON b.id = q.battery_id
		WHERE `+where+` ORDER BY q.submitted_at DESC, q.id DESC LIMIT `+strconv.Itoa(ScorePointLimit), values)
	if err != nil {
		return nil, err
	}
	type latestRow struct {
		id          uuid.UUID
		name        string
		submittedAt time.Time
		metrics     string
	}
	var latest []latestRow
	for rows.Next() {
		var row latestRow
		if err := rows.Scan(&row.id, &row.name, &row.submittedAt, &row.metrics); err != nil {
			rows.Close()
			return nil, err
		}
		latest = append(latest, row)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	slices.Reverse(latest)
	points := map[string][]PointOut{}
	for name := range metrics {
		points[name] = []PointOut{}
	}
	for _, row := range latest {
		document, err := ojson.Parse([]byte(row.metrics))
		if err != nil || document.Kind != "object" {
			continue
		}
		for _, name := range document.Keys {
			value := document.Get(name)
			if t := metrics[name]; t != nil && kindOf(value) == t.kind {
				points[name] = append(points[name], PointOut{row.id, row.name, httpx.Time{Time: row.submittedAt}, value.Raw()})
			}
		}
	}

	position := func(name string) int {
		if i := slices.Index(labelOrder, name); i >= 0 {
			return i
		}
		return len(labelOrder)
	}
	sort.SliceStable(order, func(i, j int) bool {
		a, b := position(order[i]), position(order[j])
		if a != b {
			return a < b
		}
		return order[i] < order[j]
	})
	out := &ScoresOut{QuestionnaireTypeID: typeID, Metrics: []MetricOut{}}
	for _, name := range order {
		t := metrics[name]
		label, ok := labels[name]
		if !ok {
			label = name
		}
		metric := MetricOut{Name: name, Label: label, Kind: t.kind, Count: t.count, Points: points[name]}
		if t.kind == "numeric" {
			mean := Round(t.sum/float64(t.count), 2)
			metric.Mean = &mean
		} else {
			buckets := make([]string, 0, len(t.distribution))
			for key := range t.distribution {
				buckets = append(buckets, key)
			}
			sort.Slice(buckets, func(i, j int) bool {
				a, b := t.distribution[buckets[i]], t.distribution[buckets[j]]
				if a.count != b.count {
					return a.count > b.count
				}
				return buckets[i] < buckets[j]
			})
			metric.Distribution = make([]DistributionOut, len(buckets))
			for i, key := range buckets {
				metric.Distribution[i] = DistributionOut{t.distribution[key].value.Raw(), t.distribution[key].count}
			}
		}
		out.Metrics = append(out.Metrics, metric)
	}
	return out, nil
}

// metricLabels maps `calculatedValues` names to display labels, in definition order.
func metricLabels(questionnaireJSON string) (map[string]string, []string) {
	labels := map[string]string{}
	var order []string
	document, err := ojson.Parse([]byte(questionnaireJSON))
	definitions := document.Get("calculatedValues")
	if err != nil || definitions == nil || definitions.Kind != "array" {
		return labels, order
	}
	for _, definition := range definitions.Items {
		key, ok := definition.StringField("name")
		if !ok {
			continue
		}
		label := key
		if title := definition.Get("title"); title != nil && title.Truthy() {
			if title.Kind == "string" {
				label = title.Str
			} else {
				label = string(title.Raw())
			}
		}
		if _, seen := labels[key]; !seen {
			order = append(order, key)
		}
		labels[key] = label
	}
	return labels, order
}
