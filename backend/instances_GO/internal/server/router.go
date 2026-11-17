// Package server is the HTTP side: routing as ASP.NET's endpoint routing does it (so 404s
// and 405s match instances_NET), host filtering, CORS, owner auth and the request metrics.
package server

import (
	"errors"
	"log/slog"
	"net/http"
	"sort"
	"strings"
	"time"

	"github.com/google/uuid"

	"instances/internal/httpx"
)

// Access says who may call a route.
type Access int

const (
	// Owner needs an access token from `catalog`, for an owner not blocked.
	Owner Access = iota
	// Anyone needs nothing: share links and the health check.
	Anyone
	// Peer needs `catalog`'s own bearer token (`/internal/`).
	Peer
)

// Request is one call to a handler.
type Request struct {
	W      http.ResponseWriter
	R      *http.Request
	Params map[string]string
	// Owner is the token's owner, on Owner routes.
	Owner uuid.UUID
}

// Param is a path parameter.
func (r *Request) Param(name string) string { return r.Params[name] }

// Handler serves a route. A returned *httpx.Error is written as its JSON body.
type Handler func(*Request) error

// Route is one endpoint: a method and a template such as `api/questionnaires/{id}`.
type Route struct {
	Method   string
	Template string
	Access   Access
	Handle   Handler
	segments []segment
}

type segment struct {
	literal string
	param   string
	guid    bool
}

// rank orders segments as ASP.NET's precedence does: literal, constrained, plain.
func (s segment) rank() int {
	switch {
	case s.param == "":
		return 0
	case s.guid:
		return 1
	}
	return 2
}

func parse(template string) []segment {
	var segments []segment
	for _, part := range strings.Split(strings.Trim(template, "/"), "/") {
		if strings.HasPrefix(part, "{") && strings.HasSuffix(part, "}") {
			name, constraint, _ := strings.Cut(part[1:len(part)-1], ":")
			segments = append(segments, segment{param: name, guid: constraint == "guid"})
		} else {
			segments = append(segments, segment{literal: strings.ToLower(part)})
		}
	}
	return segments
}

func (route *Route) match(parts []string) (map[string]string, bool) {
	if len(parts) != len(route.segments) {
		return nil, false
	}
	var params map[string]string
	for i, seg := range route.segments {
		part := parts[i]
		if seg.param == "" {
			if strings.ToLower(part) != seg.literal {
				return nil, false
			}
			continue
		}
		if part == "" {
			return nil, false
		}
		if seg.guid {
			if _, ok := ParseGUID(part); !ok {
				return nil, false
			}
		}
		if params == nil {
			params = map[string]string{}
		}
		params[seg.param] = part
	}
	return params, true
}

// Router picks a route as ASP.NET does: every route whose template matches the path is a
// candidate, by precedence; the method narrows them; a path with no route for the method
// is a 405, one with no route at all a 404. Each request is counted under its template.
type Router struct {
	routes []*Route
	auth   *Auth
	peer   string
}

// NewRouter sorts the routes by precedence.
func NewRouter(routes []*Route, auth *Auth, inboundPeerToken string) *Router {
	for _, route := range routes {
		route.segments = parse(route.Template)
	}
	sort.SliceStable(routes, func(i, j int) bool {
		a, b := routes[i].segments, routes[j].segments
		for k := 0; k < len(a) && k < len(b); k++ {
			if a[k].rank() != b[k].rank() {
				return a[k].rank() < b[k].rank()
			}
		}
		return len(a) > len(b)
	})
	return &Router{routes: routes, auth: auth, peer: inboundPeerToken}
}

func (rt *Router) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	started := time.Now()
	recorder := &httpx.StatusRecorder{ResponseWriter: w}
	view := "<unmatched>"
	defer func() {
		if p := recover(); p != nil {
			slog.Error("request failed", "path", r.URL.Path, "panic", p)
			if recorder.Status == 0 {
				recorder.WriteHeader(http.StatusInternalServerError)
			}
		}
		httpx.ObserveRequest(view, r.Method, recorder.Status, time.Since(started))
	}()

	parts := strings.Split(strings.Trim(r.URL.Path, "/"), "/")
	var allowed []string
	var chosen *Route
	var params map[string]string
	for _, route := range rt.routes {
		p, ok := route.match(parts)
		if !ok {
			continue
		}
		if route.Method != r.Method {
			allowed = append(allowed, route.Method)
			continue
		}
		chosen, params = route, p
		break
	}
	if chosen == nil {
		if len(allowed) > 0 {
			recorder.Header().Set("Allow", strings.Join(allowed, ", "))
			recorder.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		recorder.WriteHeader(http.StatusNotFound)
		return
	}
	view = "/" + strings.Trim(chosen.Template, "/")
	request := &Request{W: recorder, R: r, Params: params}
	if err := rt.authorize(chosen, request); err != nil {
		writeError(recorder, err)
		return
	}
	if err := chosen.Handle(request); err != nil {
		writeError(recorder, err)
	}
}

func (rt *Router) authorize(route *Route, request *Request) error {
	switch route.Access {
	case Owner:
		owner, err := rt.auth.Owner(request.R)
		if err != nil {
			return err
		}
		request.Owner = owner
	case Peer:
		if !PeerTokenValid(request.R, rt.peer) {
			return httpx.Detail(http.StatusForbidden, httpx.MsgForbidden)
		}
	}
	return nil
}

func writeError(w http.ResponseWriter, err error) {
	var unauthorized *challengeError
	if errors.As(err, &unauthorized) {
		w.Header().Set("WWW-Authenticate", `Bearer realm="api"`)
		httpx.WriteJSON(w, http.StatusUnauthorized, unauthorized.body)
		return
	}
	var api *httpx.Error
	if errors.As(err, &api) {
		httpx.WriteJSON(w, api.Status, api.Body)
		return
	}
	slog.Error("request failed", "error", err)
	w.WriteHeader(http.StatusInternalServerError)
}

// ParseGUID reads a uuid in any spelling .NET's Guid.TryParse takes: 32 hex digits, with
// dashes, or in braces or parentheses.
func ParseGUID(text string) (uuid.UUID, bool) {
	trimmed := strings.TrimSpace(text)
	if len(trimmed) == 38 && ((trimmed[0] == '{' && trimmed[37] == '}') || (trimmed[0] == '(' && trimmed[37] == ')')) {
		trimmed = trimmed[1:37]
	}
	if len(trimmed) != 32 && len(trimmed) != 36 {
		return uuid.UUID{}, false
	}
	id, err := uuid.Parse(trimmed)
	return id, err == nil
}
