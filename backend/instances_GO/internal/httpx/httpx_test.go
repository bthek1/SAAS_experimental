package httpx_test

import (
	"net/http"
	"net/http/httptest"
	"net/netip"
	"testing"
	"time"

	"instances/internal/httpx"
)

func TestFormatIsPythonsIsoformat(t *testing.T) {
	whole := time.Date(2026, 11, 17, 7, 6, 43, 0, time.UTC)
	if got := httpx.Format(whole); got != "2026-11-17T07:06:43Z" {
		t.Fatal(got)
	}
	micro := whole.Add(1230 * time.Microsecond)
	if got := httpx.Format(micro); got != "2026-11-17T07:06:43.001230Z" {
		t.Fatal(got)
	}
	brisbane := whole.In(time.FixedZone("AEST", 10*3600))
	if got := httpx.Format(brisbane); got != "2026-11-17T17:06:43+10:00" {
		t.Fatal(got)
	}
	west := whole.In(time.FixedZone("", -(3*3600 + 30*60)))
	if got := httpx.Format(west); got != "2026-11-17T03:36:43-03:30" {
		t.Fatal(got)
	}
}

func TestQuotePlus(t *testing.T) {
	if got := httpx.QuotePlus("a b/c~é&"); got != "a+b%2Fc~%C3%A9%26" {
		t.Fatal(got)
	}
}

func TestEncodeDoesNotEscapeHTML(t *testing.T) {
	if got := string(httpx.Encode(map[string]string{"a": "<b>&"})); got != `{"a":"<b>&"}` {
		t.Fatal(got)
	}
}

func TestPagesLinkOnTheRequestsHostWithSortedKeys(t *testing.T) {
	r := httptest.NewRequest(http.MethodGet, "http://api.local:8005/api/x/?submitted=true&page=2&page_size=1&a=1", nil)
	p, err := httpx.PaginationFrom(r)
	if err != nil || p.Number != 2 || p.Size != 1 || p.Skip() != 1 {
		t.Fatalf("%+v %v", p, err)
	}
	page, err := httpx.BuildPage(r, p, 3, []int{2})
	if err != nil {
		t.Fatal(err)
	}
	if *page.Next != "http://api.local:8005/api/x/?a=1&page=3&page_size=1&submitted=true" {
		t.Fatal(*page.Next)
	}
	// Page 1 drops the parameter, as DRF does.
	if *page.Previous != "http://api.local:8005/api/x/?a=1&page_size=1&submitted=true" {
		t.Fatal(*page.Previous)
	}
	if _, err := httpx.BuildPage(r, httpx.Pagination{Number: 4, Size: 1}, 3, []int{}); err == nil {
		t.Fatal("page 4 of 3 was served")
	}
	for _, bad := range []string{"0", "-1", "x"} {
		if _, err := httpx.PaginationFrom(httptest.NewRequest(http.MethodGet, "/?page="+bad, nil)); err == nil {
			t.Errorf("page=%s was accepted", bad)
		}
	}
	big, _ := httpx.PaginationFrom(httptest.NewRequest(http.MethodGet, "/?page_size=1000", nil))
	if big.Size != httpx.MaxPageSize {
		t.Fatal(big.Size)
	}
}

func TestFieldErrorsKeepTheirOrder(t *testing.T) {
	var errors httpx.FieldErrors
	errors.Add("name", "a")
	errors.Add("answers", "b")
	errors.Add("name", "c")
	if got := string(httpx.Encode(&errors)); got != `{"name":["a","c"],"answers":["b"]}` {
		t.Fatal(got)
	}
}

func TestMetricsAnswerOnlyAllowedDirectPeers(t *testing.T) {
	allowed := []netip.Prefix{netip.MustParsePrefix("127.0.0.1/32")}
	next := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusTeapot) })
	handler := httpx.MetricsEndpoint(allowed, next)
	call := func(method, path, remote string, header string) int {
		r := httptest.NewRequest(method, path, nil)
		r.RemoteAddr = remote
		if header != "" {
			r.Header.Set(header, "203.0.113.9")
		}
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		return w.Code
	}
	if code := call(http.MethodGet, "/metrics", "127.0.0.1:5000", ""); code != http.StatusOK {
		t.Fatal(code)
	}
	if code := call(http.MethodGet, "/metrics/", "[::ffff:127.0.0.1]:5000", ""); code != http.StatusOK {
		t.Fatal("an IPv4-mapped peer", code)
	}
	for _, header := range []string{"X-Forwarded-For", "X-Real-IP", "Forwarded"} {
		if code := call(http.MethodGet, "/metrics", "127.0.0.1:5000", header); code != http.StatusNotFound {
			t.Fatal(header, code)
		}
	}
	if code := call(http.MethodGet, "/metrics", "10.0.0.5:5000", ""); code != http.StatusNotFound {
		t.Fatal(code)
	}
	if code := call(http.MethodPost, "/metrics", "127.0.0.1:5000", ""); code != http.StatusNotFound {
		t.Fatal(code)
	}
	if code := call(http.MethodGet, "/other", "10.0.0.5:5000", ""); code != http.StatusTeapot {
		t.Fatal(code)
	}
}
