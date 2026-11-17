// Package dashboard is the owner's aggregates, as instances_NET's DashboardService.cs (and
// Django's dashboard.py before it) build them (#19).
//
// A window of `days` starts at midnight in `tz`, `days - 1` days ago, so "7" is today plus
// the six days before it; none means all time. `submissionsByDay` buckets by date in `tz`.
// KPIs and per-type counts follow a cohort, the questionnaires *created* in the window and
// how many of those were submitted, whenever; activity (`submissionsByDay`,
// `recentSubmissions`) counts by `submitted_at`. Pending items older than a week are
// listed whatever the window. Work on a miss is bounded by the page, not the owner's rows:
// the database counts, sorts and buckets.
package dashboard

import (
	"context"
	"math"
	"regexp"
	"strconv"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"instances/internal/httpx"
)

// ScorePointLimit is how many of the latest rows `scores` returns as points.
const ScorePointLimit = 500

const (
	listLimit      = 10
	staleAfterDays = 7
)

// Service reads the aggregates.
type Service struct{ Pool *pgxpool.Pool }

// Bodies, as Django's dashboard.py built them. `range` carries the requested zone's
// offset; every other timestamp is UTC, as elsewhere.

type SummaryOut struct {
	Range             RangeOut              `json:"range"`
	Kpis              KpisOut               `json:"kpis"`
	SubmissionsByDay  []DayOut              `json:"submissionsByDay"`
	ByQuestionnaire   []TypeCountOut        `json:"byQuestionnaireType"`
	ByBatteryType     []BatteryTypeCountOut `json:"byBatteryType"`
	RecentSubmissions []RecentOut           `json:"recentSubmissions"`
	StalePending      []StaleOut            `json:"stalePending"`
}

type RangeOut struct {
	Days *int         `json:"days"`
	From *httpx.Zoned `json:"from"`
	To   httpx.Zoned  `json:"to"`
}

type KpisOut struct {
	QuestionnairesSent      int      `json:"questionnairesSent"`
	QuestionnairesSubmitted int      `json:"questionnairesSubmitted"`
	QuestionnairesPending   int      `json:"questionnairesPending"`
	CompletionRate          float64  `json:"completionRate"`
	MedianHoursToComplete   *float64 `json:"medianHoursToComplete"`
	BatteriesTotal          int      `json:"batteriesTotal"`
	BatteriesComplete       int      `json:"batteriesComplete"`
	BatteriesInProgress     int      `json:"batteriesInProgress"`
	BatteriesNotStarted     int      `json:"batteriesNotStarted"`
}

type DayOut struct {
	Date  httpx.Date `json:"date"`
	Count int        `json:"count"`
}

type TypeCountOut struct {
	ID        uuid.UUID `json:"id"`
	Title     string    `json:"title"`
	Sent      int       `json:"sent"`
	Submitted int       `json:"submitted"`
	Pending   int       `json:"pending"`
}

type BatteryTypeCountOut struct {
	ID         uuid.UUID `json:"id"`
	Title      string    `json:"title"`
	Complete   int       `json:"complete"`
	InProgress int       `json:"inProgress"`
	NotStarted int       `json:"notStarted"`
}

type RecentOut struct {
	ID                     uuid.UUID  `json:"id"`
	Name                   string     `json:"name"`
	QuestionnaireTypeTitle string     `json:"questionnaireTypeTitle"`
	SubmittedAt            httpx.Time `json:"submittedAt"`
}

type StaleOut struct {
	ID                     uuid.UUID  `json:"id"`
	Name                   string     `json:"name"`
	QuestionnaireTypeTitle string     `json:"questionnaireTypeTitle"`
	ShareToken             uuid.UUID  `json:"shareToken"`
	CreatedAt              httpx.Time `json:"createdAt"`
	AgeDays                int        `json:"ageDays"`
}

// nowIn is now, to the microsecond, in the zone.
func nowIn(zone *time.Location) time.Time { return httpx.Now().In(zone) }

// WindowStart is midnight in the zone, days-1 days before now's date; nil for all time.
func WindowStart(days *int, now time.Time, zone *time.Location) *time.Time {
	if days == nil {
		return nil
	}
	date := time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, time.UTC).AddDate(0, 0, -(*days - 1))
	start := AtWallTime(date.Year(), date.Month(), date.Day(), 0, 0, 0, 0, zone)
	return &start
}

// filters is the SQL that narrows each part of the summary. Placeholders are named
// (`:owner`), and bind numbers only the ones a query uses: Postgres refuses a parameter
// that a statement never mentions.
type filters struct {
	values                                                   map[string]any
	questionnaires, batteries, qtypes, btypes, cohort, inWin string
}

var placeholder = regexp.MustCompile(`:[a-z]+`)

// bind turns `:name` placeholders into `$n`, with the arguments in that order.
func bind(sql string, values map[string]any) (string, []any) {
	var args []any
	numbers := map[string]string{}
	bound := placeholder.ReplaceAllStringFunc(sql, func(name string) string {
		value, ok := values[name[1:]]
		if !ok {
			return name
		}
		if n, seen := numbers[name]; seen {
			return n
		}
		args = append(args, value)
		numbers[name] = "$" + strconv.Itoa(len(args))
		return numbers[name]
	})
	return bound, args
}

func (s *Service) query(ctx context.Context, sql string, values map[string]any) (pgx.Rows, error) {
	bound, args := bind(sql, values)
	return s.Pool.Query(ctx, bound, args...)
}

// Summary is `/api/dashboard/`.
func (s *Service) Summary(ctx context.Context, owner uuid.UUID, days *int, typeID *uuid.UUID,
	zone *time.Location, zoneName string) (*SummaryOut, error) {
	now := nowIn(zone)
	start := WindowStart(days, now, zone)

	f := &filters{values: map[string]any{"owner": owner, "zone": zoneName}}
	const o, t = ":owner", ":type"
	f.questionnaires = "q.owner_id = " + o
	f.batteries = "b.owner_id = " + o
	f.qtypes = "t.owner_id = " + o
	f.btypes = "t.owner_id = " + o
	if typeID != nil {
		f.values["type"] = *typeID
		f.questionnaires += " AND q.questionnaire_type_id = " + t
		// A subquery rather than a join, so the slot counts below still see every
		// questionnaire in the battery, not just the ones of this type.
		f.batteries += " AND EXISTS (SELECT 1 FROM questionnaires_questionnaire x WHERE x.questionnaire_type_id = " +
			t + " AND x.battery_id = b.id)"
		f.qtypes += " AND t.id = " + t
		f.btypes += " AND EXISTS (SELECT 1 FROM questionnaires_batterytyperefslot s WHERE s.questionnaire_type_id = " +
			t + " AND s.battery_type_id = t.id)"
	}
	f.cohort = f.questionnaires
	f.inWin = f.questionnaires + " AND q.submitted_at IS NOT NULL"
	createdSince := "TRUE"
	if start != nil {
		const from = ":from"
		f.values["from"] = start.UTC()
		f.cohort += " AND q.created_at >= " + from
		f.inWin += " AND q.submitted_at >= " + from
		f.batteries += " AND b.created_at >= " + from
		createdSince = "x.created_at >= " + from
	}

	var sent, submitted int
	counts, args := bind(`SELECT count(*), count(*) FILTER (WHERE q.submitted_at IS NOT NULL)
		FROM questionnaires_questionnaire q WHERE `+f.cohort, f.values)
	if err := s.Pool.QueryRow(ctx, counts, args...).Scan(&sent, &submitted); err != nil {
		return nil, err
	}

	rows, err := s.query(ctx, `SELECT t.id, t.title,
		    (SELECT count(*) FROM questionnaires_questionnaire x
		     WHERE x.questionnaire_type_id = t.id AND x.owner_id = `+o+` AND `+createdSince+`),
		    (SELECT count(*) FROM questionnaires_questionnaire x
		     WHERE x.questionnaire_type_id = t.id AND x.owner_id = `+o+` AND `+createdSince+` AND x.submitted_at IS NOT NULL)
		FROM questionnaires_questionnairetyperef t WHERE `+f.qtypes+` ORDER BY t.title`, f.values)
	if err != nil {
		return nil, err
	}
	byType, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (TypeCountOut, error) {
		var t TypeCountOut
		err := row.Scan(&t.ID, &t.Title, &t.Sent, &t.Submitted)
		t.Pending = t.Sent - t.Submitted
		return t, err
	})
	if err != nil {
		return nil, err
	}

	// The owner sits on the join: stale planner statistics must not turn this into a
	// scan of every owner's questionnaires.
	rows, err = s.query(ctx, `SELECT b.battery_type_id,
		    (SELECT count(*) FROM questionnaires_questionnaire x WHERE x.battery_id = b.id AND x.owner_id = `+o+`),
		    (SELECT count(*) FROM questionnaires_questionnaire x
		     WHERE x.battery_id = b.id AND x.owner_id = `+o+` AND x.submitted_at IS NOT NULL)
		FROM questionnaires_battery b WHERE `+f.batteries, f.values)
	if err != nil {
		return nil, err
	}
	type batteryCounts struct {
		typeID           uuid.UUID
		total, submitted int
	}
	batteryRows, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (batteryCounts, error) {
		var b batteryCounts
		return b, row.Scan(&b.typeID, &b.total, &b.submitted)
	})
	if err != nil {
		return nil, err
	}
	statusByType := map[uuid.UUID]*BatteryTypeCountOut{}
	var kpis BatteryTypeCountOut
	for _, row := range batteryRows {
		bucket := statusByType[row.typeID]
		if bucket == nil {
			bucket = &BatteryTypeCountOut{}
			statusByType[row.typeID] = bucket
		}
		for _, counts := range []*BatteryTypeCountOut{&kpis, bucket} {
			switch {
			case row.total > 0 && row.submitted == row.total:
				counts.Complete++
			case row.submitted == 0:
				counts.NotStarted++
			default:
				counts.InProgress++
			}
		}
	}
	rows, err = s.query(ctx, `SELECT t.id, t.title FROM questionnaires_batterytyperef t WHERE `+f.btypes+
		` ORDER BY t.title`, f.values)
	if err != nil {
		return nil, err
	}
	byBatteryType, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (BatteryTypeCountOut, error) {
		var t BatteryTypeCountOut
		if err := row.Scan(&t.ID, &t.Title); err != nil {
			return t, err
		}
		if counts := statusByType[t.ID]; counts != nil {
			t.Complete, t.InProgress, t.NotStarted = counts.Complete, counts.InProgress, counts.NotStarted
		}
		return t, nil
	})
	if err != nil {
		return nil, err
	}

	// Questionnaires made by a battery have no name of their own: show the battery's.
	const name = `CASE WHEN q.name <> '' THEN q.name ELSE coalesce(b.name, '') END`
	const joins = ` FROM questionnaires_questionnaire q
		JOIN questionnaires_questionnairetyperef t ON t.id = q.questionnaire_type_id
		LEFT JOIN questionnaires_battery b ON b.id = q.battery_id `
	rows, err = s.query(ctx, `SELECT q.id, `+name+`, t.title, q.submitted_at`+joins+`WHERE `+f.inWin+
		` ORDER BY q.submitted_at DESC LIMIT `+strconv.Itoa(listLimit), f.values)
	if err != nil {
		return nil, err
	}
	recent, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (RecentOut, error) {
		var r RecentOut
		return r, row.Scan(&r.ID, &r.Name, &r.QuestionnaireTypeTitle, &r.SubmittedAt.Time)
	})
	if err != nil {
		return nil, err
	}

	f.values["stale"] = WallDaysBefore(now, staleAfterDays, zone).UTC()
	rows, err = s.query(ctx, `SELECT q.id, `+name+`, t.title, q.share_token, q.created_at`+joins+`WHERE `+
		f.questionnaires+` AND q.submitted_at IS NULL AND q.created_at < :stale
		ORDER BY q.created_at LIMIT `+strconv.Itoa(listLimit), f.values)
	if err != nil {
		return nil, err
	}
	nowUTC := now.UTC()
	stale, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (StaleOut, error) {
		var s StaleOut
		err := row.Scan(&s.ID, &s.Name, &s.QuestionnaireTypeTitle, &s.ShareToken, &s.CreatedAt.Time)
		s.AgeDays = int(math.Floor(nowUTC.Sub(s.CreatedAt.Time).Hours() / 24))
		return s, err
	})
	if err != nil {
		return nil, err
	}

	median, err := s.medianHours(ctx, f.cohort+" AND q.submitted_at IS NOT NULL", f.values, submitted)
	if err != nil {
		return nil, err
	}
	byDay, err := s.submissionsByDay(ctx, f.inWin, f.values, start, now)
	if err != nil {
		return nil, err
	}

	rate := 0.0
	if sent > 0 {
		rate = Round(float64(submitted)/float64(sent), 4)
	}
	var from *httpx.Zoned
	if start != nil {
		from = &httpx.Zoned{Time: *start}
	}
	return &SummaryOut{
		Range: RangeOut{Days: days, From: from, To: httpx.Zoned{Time: now}},
		Kpis: KpisOut{
			QuestionnairesSent: sent, QuestionnairesSubmitted: submitted, QuestionnairesPending: sent - submitted,
			CompletionRate: rate, MedianHoursToComplete: median,
			BatteriesTotal:    kpis.Complete + kpis.InProgress + kpis.NotStarted,
			BatteriesComplete: kpis.Complete, BatteriesInProgress: kpis.InProgress, BatteriesNotStarted: kpis.NotStarted,
		},
		SubmissionsByDay:  byDay,
		ByQuestionnaire:   nonNil(byType),
		ByBatteryType:     nonNil(byBatteryType),
		RecentSubmissions: nonNil(recent),
		StalePending:      nonNil(stale),
	}, nil
}

func nonNil[T any](items []T) []T {
	if items == nil {
		return []T{}
	}
	return items
}

// medianHours is sorted in the database, so only the middle one or two rows come back.
func (s *Service) medianHours(ctx context.Context, where string, values map[string]any, count int) (*float64, error) {
	if count == 0 {
		return nil, nil
	}
	skip := (count - 1) / 2
	take := count/2 + 1 - skip
	rows, err := s.query(ctx, `SELECT extract(epoch FROM q.submitted_at - q.created_at)::float8
		FROM questionnaires_questionnaire q WHERE `+where+`
		ORDER BY q.submitted_at - q.created_at OFFSET `+strconv.Itoa(skip)+` LIMIT `+strconv.Itoa(take), values)
	if err != nil {
		return nil, err
	}
	middle, err := pgx.CollectRows(rows, pgx.RowTo[float64])
	if err != nil || len(middle) == 0 {
		return nil, err
	}
	sum := 0.0
	for _, seconds := range middle {
		sum += seconds
	}
	hours := Round(sum/float64(len(middle))/3600, 1)
	return &hours, nil
}

func (s *Service) submissionsByDay(ctx context.Context, where string, values map[string]any, start *time.Time,
	now time.Time) ([]DayOut, error) {
	rows, err := s.query(ctx, `SELECT (q.submitted_at AT TIME ZONE :zone::text)::date AS day, count(*)
		FROM questionnaires_questionnaire q WHERE `+where+` GROUP BY day`, values)
	if err != nil {
		return nil, err
	}
	counts := map[string]int{}
	var first time.Time
	for rows.Next() {
		var day time.Time
		var n int
		if err := rows.Scan(&day, &n); err != nil {
			rows.Close()
			return nil, err
		}
		counts[day.Format("2006-01-02")] = n
		if first.IsZero() || day.Before(first) {
			first = day
		}
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	if len(counts) == 0 && start == nil {
		return []DayOut{}, nil
	}
	day := first
	if start != nil {
		day = time.Date(start.Year(), start.Month(), start.Day(), 0, 0, 0, 0, time.UTC)
	}
	today := time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, time.UTC)
	series := []DayOut{}
	for ; !day.After(today); day = day.AddDate(0, 0, 1) {
		series = append(series, DayOut{Date: httpx.Date{Time: day}, Count: counts[day.Format("2006-01-02")]})
	}
	return series, nil
}
