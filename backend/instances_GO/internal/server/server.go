package server

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"instances/internal/config"
	"instances/internal/httpx"
)

// KeepAliveSeconds outlasts the gateway's upstream keepalive_timeout, as Kestrel's 75 s
// does, or a request can arrive just as the server closes the connection: a 502 (#24,
// tests/test_go_keepalive.py).
const KeepAliveSeconds = 75

// ListenAddress reads ASPNETCORE_URLS, as instances_NET does, so one env file runs either
// (#52): the first `http://host:port`. ASP.NET's default when it is unset is localhost:5000.
func ListenAddress(urls string) (string, error) {
	first := strings.TrimSpace(strings.Split(urls, ";")[0])
	if first == "" {
		return "localhost:5000", nil
	}
	parsed, err := url.Parse(strings.Replace(strings.Replace(first, "://*", "://0.0.0.0", 1), "://+", "://0.0.0.0", 1))
	if err != nil || parsed.Scheme != "http" || parsed.Port() == "" {
		return "", fmt.Errorf("ASPNETCORE_URLS: %q is not http://host:port", first)
	}
	return parsed.Host, nil
}

// New is the HTTP server for these routes.
func New(settings *config.Settings, address string, routes []*Route, auth *Auth) *http.Server {
	router := NewRouter(routes, auth, settings.InboundPeerToken)
	return &http.Server{
		Addr:              address,
		Handler:           Pipeline(settings, router),
		ReadHeaderTimeout: 30 * time.Second,
		IdleTimeout:       KeepAliveSeconds * time.Second,
	}
}

// Health is `/internal/health/`: anyone may ask.
func Health(r *Request) error {
	httpx.WriteJSON(r.W, http.StatusOK, map[string]string{"status": "ok"})
	return nil
}

// HealthCheck is the `health` verb: a container health check, since a minimal image has
// no curl. 0 when the URL answers 2xx.
func HealthCheck(ctx context.Context, target string) int {
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, target, nil)
	if err != nil {
		return 1
	}
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		return 1
	}
	defer response.Body.Close()
	if response.StatusCode >= 200 && response.StatusCode < 300 {
		return 0
	}
	return 1
}
