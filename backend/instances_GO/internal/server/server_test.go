package server

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"instances/internal/httpx"
)

func named(method, template, name string) *Route {
	return &Route{Method: method, Template: template, Access: Anyone, Handle: func(r *Request) error {
		httpx.WriteJSON(r.W, http.StatusOK, map[string]string{"route": name, "id": r.Param("id")})
		return nil
	}}
}

func TestRoutingAsASPNETDoes(t *testing.T) {
	router := NewRouter([]*Route{
		named(http.MethodGet, "api/q/{id}", "detail"),
		named(http.MethodGet, "api/q/by-token/{t}", "public"),
		named(http.MethodPatch, "api/q/{id}", "update"),
		named(http.MethodPost, "internal/refs/{kind}/{refId:guid}/retire", "retire"),
	}, nil, "")
	call := func(method, path string) (int, string) {
		w := httptest.NewRecorder()
		router.ServeHTTP(w, httptest.NewRequest(method, path, nil))
		return w.Code, w.Body.String()
	}
	if code, body := call(http.MethodGet, "/API/Q/by-token/x/"); code != 200 || body != `{"id":"","route":"public"}` {
		t.Fatal("a literal beats a parameter, case-insensitively:", code, body)
	}
	if code, body := call(http.MethodGet, "/api/q/abc"); code != 200 || body != `{"id":"abc","route":"detail"}` {
		t.Fatal(code, body)
	}
	if code, _ := call(http.MethodPut, "/api/q/abc/"); code != http.StatusMethodNotAllowed {
		t.Fatal("a known path with another method is 405:", code)
	}
	if code, _ := call(http.MethodGet, "/api/nothing/"); code != http.StatusNotFound {
		t.Fatal(code)
	}
	if code, _ := call(http.MethodPost, "/internal/refs/x/not-a-guid/retire/"); code != http.StatusNotFound {
		t.Fatal("a guid constraint that fails is no match:", code)
	}
	if code, _ := call(http.MethodGet, "/internal/refs/x/0b5e8f3e-6d2c-4f0e-9d8f-1a2b3c4d5e6f/retire/"); code != http.StatusMethodNotAllowed {
		t.Fatal(code)
	}
}

func TestGUIDSpellings(t *testing.T) {
	for _, text := range []string{
		"0b5e8f3e-6d2c-4f0e-9d8f-1a2b3c4d5e6f", "0b5e8f3e6d2c4f0e9d8f1a2b3c4d5e6f",
		"{0b5e8f3e-6d2c-4f0e-9d8f-1a2b3c4d5e6f}", "(0B5E8F3E-6D2C-4F0E-9D8F-1A2B3C4D5E6F)",
	} {
		if _, ok := ParseGUID(text); !ok {
			t.Errorf("%s was refused", text)
		}
	}
	for _, text := range []string{"", "x", "urn:uuid:0b5e8f3e-6d2c-4f0e-9d8f-1a2b3c4d5e6f", "0b5e8f3e"} {
		if _, ok := ParseGUID(text); ok {
			t.Errorf("%s was accepted", text)
		}
	}
}

func TestHostFilter(t *testing.T) {
	for host, ok := range map[string]bool{
		"localhost": true, "LOCALHOST:8000": true, "127.0.0.1:9": true, "evil.example": false, "": false,
		"a.loadtest.internal": true,
	} {
		if hostAllowed(host, []string{"localhost", "127.0.0.1", "*.loadtest.internal"}) != ok {
			t.Errorf("%q: want %v", host, ok)
		}
	}
}

func TestListenAddress(t *testing.T) {
	for urls, want := range map[string]string{
		"":                      "localhost:5000",
		"http://127.0.0.1:8017": "127.0.0.1:8017",
		"http://0.0.0.0:8000;x": "0.0.0.0:8000",
		"http://*:8000":         "0.0.0.0:8000",
	} {
		if got, err := ListenAddress(urls); err != nil || got != want {
			t.Errorf("%q: %q %v", urls, got, err)
		}
	}
	if _, err := ListenAddress("https://0.0.0.0:443"); err == nil {
		t.Error("https was accepted: this server has no certificate")
	}
}
