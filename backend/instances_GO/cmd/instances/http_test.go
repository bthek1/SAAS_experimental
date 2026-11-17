package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"instances/internal/cache"
	"instances/internal/config"
	"instances/internal/server"
	"instances/internal/store"
	"instances/internal/testdb"
)

func TestMain(m *testing.M) {
	code := m.Run()
	testdb.StopShared()
	os.Exit(code)
}

const backend = "../../.."

// testApp is the real service on a throwaway database, with every statement counted.
type testApp struct {
	*App
	server  *httptest.Server
	queries atomic.Pointer[atomic.Int64]
	signer  any
	store   *memoryStore
}

func newTestApp(t *testing.T) *testApp {
	t.Helper()
	db := testdb.Start(t)
	_, url := db.Migrated(t)
	settings, err := config.LoadFrom(map[string]string{"SETTINGS": "test", "INSTANCES_DATABASE_URL": url,
		"CATALOG_INTERNAL_URL": "http://127.0.0.1:9"}, nil)
	if err != nil {
		t.Fatal(err)
	}
	app, err := NewApp(context.Background(), settings)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(app.Close)
	ta := &testApp{App: app, store: &memoryStore{values: map[string][]byte{}}}
	// A cache in memory, off as the test profile has it; cache tests turn it on.
	ta.Cache = cache.New(ta.store, true)
	ta.Cache.SetEnabled(false)
	ta.Refs.Cache, ta.Handlers.Cache = ta.Cache, ta.Cache
	handler := server.New(settings, "", app.Routes(), app.Auth).Handler
	ta.server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ctx, counter := store.CountQueries(r.Context())
		ta.queries.Store(counter)
		handler.ServeHTTP(w, r.WithContext(ctx))
	}))
	t.Cleanup(ta.server.Close)
	source, err := os.ReadFile(filepath.Join(backend, "common", "common", "dev_keys.py"))
	if err != nil {
		t.Fatal(err)
	}
	pem := regexp.MustCompile(`(?s)-----BEGIN PRIVATE KEY-----.*?-----END PRIVATE KEY-----`).Find(source)
	if ta.signer, err = jwt.ParseRSAPrivateKeyFromPEM(pem); err != nil {
		t.Fatal(err)
	}
	return ta
}

// token is an access token as `catalog` issues it.
func (a *testApp) token(owner uuid.UUID) string {
	claims := jwt.MapClaims{"token_type": "access", "jti": uuid.NewString(), "user_id": owner.String(),
		"iat": time.Now().Unix(), "exp": time.Now().Add(5 * time.Minute).Unix()}
	signed, err := jwt.NewWithClaims(jwt.SigningMethodRS256, claims).SignedString(a.signer)
	if err != nil {
		panic(err)
	}
	return signed
}

type response struct {
	Status int
	Body   map[string]any
	Raw    []byte
}

func (a *testApp) call(t *testing.T, method, path, bearer string, body any) response {
	t.Helper()
	var reader io.Reader
	if body != nil {
		encoded, _ := json.Marshal(body)
		reader = bytes.NewReader(encoded)
	}
	request, _ := http.NewRequest(method, a.server.URL+path, reader)
	request.Host = "localhost"
	if bearer != "" {
		request.Header.Set("Authorization", "Bearer "+bearer)
	}
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	resp, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	out := response{Status: resp.StatusCode, Raw: raw}
	_ = json.Unmarshal(raw, &out.Body)
	return out
}

func (a *testApp) must(t *testing.T, method, path, bearer string, body any) response {
	t.Helper()
	r := a.call(t, method, path, bearer, body)
	if r.Status >= 300 {
		t.Fatalf("%s %s: %d %s", method, path, r.Status, r.Raw)
	}
	return r
}

func (a *testApp) send(t *testing.T, event any) string {
	t.Helper()
	r := a.must(t, http.MethodPost, "/internal/events/", "test-catalog-to-instances", event)
	return r.Body["result"].(string)
}

func stamp() string { return time.Now().UTC().Format("2006-01-02T15:04:05.000000+00:00") }

func qtypeEvent(owner, id uuid.UUID, version int, definition any) map[string]any {
	return map[string]any{"type": "questionnaire_type.changed", "aggregateId": id.String(), "version": version,
		"data": map[string]any{"ownerId": owner.String(), "title": "Scale", "createdAt": stamp(), "updatedAt": stamp(),
			"questionnaireJson": definition}}
}

func btypeEvent(owner, id uuid.UUID, slots ...uuid.UUID) map[string]any {
	items := []any{}
	for i, s := range slots {
		items = append(items, map[string]any{"questionnaireTypeId": s.String(), "order": i})
	}
	return map[string]any{"type": "battery_type.changed", "aggregateId": id.String(), "version": 1,
		"data": map[string]any{"ownerId": owner.String(), "title": "Intake", "createdAt": stamp(),
			"updatedAt": stamp(), "description": "", "items": items}}
}

// seed is an owner with a scored type and a two-slot battery type.
type seed struct {
	owner, typeID, batteryTypeID uuid.UUID
	bearer                       string
}

func newSeed(t *testing.T, a *testApp) *seed {
	s := &seed{owner: uuid.New(), typeID: uuid.New(), batteryTypeID: uuid.New()}
	s.bearer = a.token(s.owner)
	scored := map[string]any{"pages": []any{}, "calculatedValues": []any{map[string]any{"name": "total", "title": "Total"}}}
	a.send(t, qtypeEvent(s.owner, s.typeID, 1, scored))
	a.send(t, btypeEvent(s.owner, s.batteryTypeID, s.typeID, s.typeID))
	return s
}

// addRows makes `count` questionnaires and as many two-slot batteries, half of the
// standalone ones submitted.
func (s *seed) addRows(t *testing.T, a *testApp, count int) {
	for i := range count {
		created := a.must(t, http.MethodPost, "/api/questionnaires/", s.bearer,
			map[string]any{"questionnaireTypeId": s.typeID.String(), "name": fmt.Sprintf("r%d", i)})
		a.must(t, http.MethodPost, "/api/batteries/", s.bearer, map[string]any{"batteryTypeId": s.batteryTypeID.String()})
		if i%2 == 0 {
			a.must(t, http.MethodPatch, fmt.Sprintf("/api/questionnaires/by-token/%s/submit/", created.Body["shareToken"]),
				"", map[string]any{"answers": map[string]any{"q1": "a"}, "metrics": map[string]any{"total": i}})
		}
	}
}

func (a *testApp) count(t *testing.T, method, path, bearer string, body any) int {
	t.Helper()
	a.must(t, method, path, bearer, body)
	return int(a.queries.Load().Load())
}

// hotPaths are the endpoints k6 loads (#9): each must cost a fixed number of queries.
func (a *testApp) hotPaths(t *testing.T, s *seed) map[string]int {
	created := a.must(t, http.MethodPost, "/api/questionnaires/", s.bearer, map[string]any{"questionnaireTypeId": s.typeID.String()})
	id, token := created.Body["id"], created.Body["shareToken"]
	return map[string]int{
		"questionnaire-list":   a.count(t, http.MethodGet, "/api/questionnaires/", s.bearer, nil),
		"questionnaire-detail": a.count(t, http.MethodGet, fmt.Sprintf("/api/questionnaires/%s/", id), s.bearer, nil),
		"battery-list":         a.count(t, http.MethodGet, "/api/batteries/", s.bearer, nil),
		"respondent-read":      a.count(t, http.MethodGet, fmt.Sprintf("/api/questionnaires/by-token/%s/", token), "", nil),
		"respondent-submit": a.count(t, http.MethodPatch, fmt.Sprintf("/api/questionnaires/by-token/%s/submit/", token), "",
			map[string]any{"answers": map[string]any{"q1": "a"}}),
		"dashboard": a.count(t, http.MethodGet, "/api/dashboard/?days=30&tz=Australia/Sydney", s.bearer, nil),
		"dashboard-scores": a.count(t, http.MethodGet,
			fmt.Sprintf("/api/dashboard/scores/?questionnaireType=%s", s.typeID), s.bearer, nil),
	}
}

func TestQueryCountsDoNotGrowWithRows(t *testing.T) {
	a := newTestApp(t)
	s := newSeed(t, a)
	s.addRows(t, a, 3)
	few := a.hotPaths(t, s)
	s.addRows(t, a, 30)
	many := a.hotPaths(t, s)
	for name, n := range few {
		if many[name] != n {
			t.Errorf("%s: %d queries with few rows, %d with many", name, n, many[name])
		}
	}
	// Each authenticated request pays one query for the blocked-owner check, no more.
	if few["questionnaire-list"] != 3 || few["questionnaire-detail"] != 2 {
		t.Errorf("list %d, detail %d: want 3 and 2, as .NET", few["questionnaire-list"], few["questionnaire-detail"])
	}
}

// Every event contract in backend/contracts/ is accepted, in the order `catalog` sends
// them, with fresh ids that keep their relations.
func TestEveryContractEventIsApplied(t *testing.T) {
	a := newTestApp(t)
	ids := map[string]string{}
	for _, name := range []string{
		"event.questionnaire_type.changed", "event.battery_type.changed", "event.battery_type.deleted",
		"event.questionnaire_type.deleted", "event.user.deactivated", "event.user.reactivated", "event.user.deleted",
	} {
		raw, err := os.ReadFile(filepath.Join(backend, "contracts", name+".json"))
		if err != nil {
			t.Fatal(err)
		}
		text := string(raw)
		for _, old := range []string{"11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222",
			"33333333-3333-3333-3333-333333333333", "44444444-4444-4444-4444-444444444444"} {
			if _, ok := ids[old]; !ok {
				ids[old] = uuid.NewString()
			}
			text = strings.ReplaceAll(text, old, ids[old])
		}
		var event any
		if err := json.Unmarshal([]byte(text), &event); err != nil {
			t.Fatal(name, err)
		}
		if result := a.send(t, event); result != "applied" {
			t.Errorf("%s: %s", name, result)
		}
	}
}

// The cache's rules (#11), through the real endpoints, as instances_NET's CacheTests.

func (a *testApp) sent(t *testing.T, s *seed) int {
	t.Helper()
	body := a.must(t, http.MethodGet, "/api/dashboard/", s.bearer, nil).Body
	return int(body["kpis"].(map[string]any)["questionnairesSent"].(float64))
}

func (a *testApp) create(t *testing.T, s *seed) map[string]any {
	t.Helper()
	return a.must(t, http.MethodPost, "/api/questionnaires/", s.bearer,
		map[string]any{"questionnaireTypeId": s.typeID.String()}).Body
}

func TestTwoOwnersNeverShareAValue(t *testing.T) {
	a := newTestApp(t)
	a.Cache.SetEnabled(true)
	one, two := newSeed(t, a), newSeed(t, a)
	a.create(t, one)
	a.create(t, one)
	if a.sent(t, one) != 2 || a.sent(t, two) != 0 || a.sent(t, one) != 2 {
		t.Fatal("an owner saw another's dashboard")
	}
	for key := range a.store.values {
		if strings.HasPrefix(key, "dashboard:") && !strings.Contains(key, one.owner.String()) &&
			!strings.Contains(key, two.owner.String()) {
			t.Errorf("a key without its owner: %s", key)
		}
	}
}

func TestAHitIsServedUntilADeleteBumpsTheGeneration(t *testing.T) {
	a := newTestApp(t)
	a.Cache.SetEnabled(true)
	s := newSeed(t, a)
	first := a.create(t, s)
	if a.sent(t, s) != 1 {
		t.Fatal("first read")
	}
	a.create(t, s)
	a.create(t, s)
	if a.sent(t, s) != 1 {
		t.Fatal("creation should not bump: the dashboard lags it by up to the TTL")
	}
	a.must(t, http.MethodDelete, fmt.Sprintf("/api/questionnaires/%s/", first["id"]), s.bearer, nil)
	if got := a.sent(t, s); got != 2 {
		t.Fatalf("after a delete: %d", got)
	}
}

func TestADeadRedisStillAnswers(t *testing.T) {
	a := newTestApp(t)
	a.Cache.SetEnabled(true)
	s := newSeed(t, a)
	a.create(t, s)
	a.store.broken = true
	if a.sent(t, s) != 1 {
		t.Fatal("dashboard")
	}
	a.must(t, http.MethodGet, fmt.Sprintf("/api/dashboard/scores/?questionnaireType=%s", s.typeID), s.bearer, nil)
}

func TestABlockedOwnerIsRefusedEvenOnAHit(t *testing.T) {
	a := newTestApp(t)
	a.Cache.SetEnabled(true)
	s := newSeed(t, a)
	a.sent(t, s)
	a.send(t, map[string]any{"type": "user.deactivated", "aggregateId": s.owner.String(), "version": 1,
		"data": map[string]any{}})
	if r := a.call(t, http.MethodGet, "/api/dashboard/", s.bearer, nil); r.Status != http.StatusUnauthorized {
		t.Fatal(r.Status)
	}
}

func TestOffMeansNothingIsStored(t *testing.T) {
	a := newTestApp(t)
	s := newSeed(t, a)
	a.sent(t, s)
	for key := range a.store.values {
		if strings.HasPrefix(key, "dashboard:") {
			t.Fatalf("stored with the cache off: %s", key)
		}
	}
}

// memoryStore is a cache store in memory, for the cache tests.
type memoryStore struct {
	values map[string][]byte
	broken bool
}

func (m *memoryStore) Get(_ context.Context, key string) ([]byte, error) {
	if m.broken {
		return nil, fmt.Errorf("redis down")
	}
	if v, ok := m.values[key]; ok {
		return v, nil
	}
	return nil, cache.ErrMiss
}

func (m *memoryStore) Set(_ context.Context, key string, value []byte, _ time.Duration) error {
	if m.broken {
		return fmt.Errorf("redis down")
	}
	m.values[key] = value
	return nil
}

func (m *memoryStore) GetOrAdd(_ context.Context, key, value string) (string, error) {
	if m.broken {
		return "", fmt.Errorf("redis down")
	}
	if v, ok := m.values[key]; ok {
		return string(v), nil
	}
	m.values[key] = []byte(value)
	return value, nil
}
