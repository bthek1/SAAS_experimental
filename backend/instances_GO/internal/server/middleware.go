package server

import (
	"net"
	"net/http"
	"os"
	"strings"

	"instances/internal/config"
	"instances/internal/httpx"
)

// Pipeline is the order instances_NET's Program.Build sets: `/metrics` first, then host
// filtering, the HTTPS redirect (prod), CORS, and the router.
func Pipeline(settings *config.Settings, router http.Handler) http.Handler {
	var handler = router
	handler = cors(settings, handler)
	if settings.HTTPSRedirect {
		handler = httpsRedirect(handler)
	}
	handler = hostFilter(settings.AllowedHosts, handler)
	return httpx.MetricsEndpoint(settings.MetricsAllowedNetworks, handler)
}

// hostFilter answers 400 to a Host header outside ALLOWED_HOSTS, as ASP.NET's host
// filtering does (no empty hosts, `*` and `*.domain` patterns).
func hostFilter(allowed []string, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !hostAllowed(r.Host, allowed) {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func hostAllowed(hostHeader string, allowed []string) bool {
	if hostHeader == "" {
		return false
	}
	host := hostHeader
	if h, _, err := net.SplitHostPort(hostHeader); err == nil {
		host = h
	}
	host = strings.ToLower(strings.Trim(host, "[]"))
	for _, pattern := range allowed {
		pattern = strings.ToLower(strings.Trim(pattern, "[]"))
		switch {
		case pattern == "*":
			return true
		case strings.HasPrefix(pattern, "*."):
			if strings.HasSuffix(host, pattern[1:]) {
				return true
			}
		case pattern == host:
			return true
		}
	}
	return false
}

// httpsRedirect is ASP.NET's UseHttpsRedirection: a 307 to HTTPS on the port named by
// HTTPS_PORT or ASPNETCORE_HTTPS_PORT; with neither set it cannot know one and does
// nothing. Between the services is a private network: `/internal/` stays plain HTTP.
func httpsRedirect(next http.Handler) http.Handler {
	port := os.Getenv("HTTPS_PORT")
	if port == "" {
		port = os.Getenv("ASPNETCORE_HTTPS_PORT")
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		internal := r.URL.Path == "/internal" || strings.HasPrefix(r.URL.Path, "/internal/")
		if port == "" || r.TLS != nil || internal {
			next.ServeHTTP(w, r)
			return
		}
		host := r.Host
		if h, _, err := net.SplitHostPort(host); err == nil {
			host = h
		}
		if port != "443" {
			host = net.JoinHostPort(host, port)
		}
		http.Redirect(w, r, "https://"+host+r.URL.RequestURI(), http.StatusTemporaryRedirect)
	})
}

// cors is the default policy: listed origins (and dev's LAN pattern), any header and
// method, and Content-Disposition exposed so the SPA can read a PDF's filename. A
// preflight is answered here, whatever the path.
func cors(settings *config.Settings, next http.Handler) http.Handler {
	allowed := func(origin string) bool {
		for _, o := range settings.CORSAllowedOrigins {
			if o == origin {
				return true
			}
		}
		for _, pattern := range settings.CORSAllowedOriginPatterns {
			if pattern.MatchString(origin) {
				return true
			}
		}
		return false
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		if origin == "" {
			next.ServeHTTP(w, r)
			return
		}
		ok := allowed(origin)
		if r.Method == http.MethodOptions && r.Header.Get("Access-Control-Request-Method") != "" {
			if ok {
				h := w.Header()
				h.Set("Access-Control-Allow-Origin", origin)
				h.Add("Vary", "Origin")
				h.Set("Access-Control-Allow-Methods", r.Header.Get("Access-Control-Request-Method"))
				if headers := r.Header.Get("Access-Control-Request-Headers"); headers != "" {
					h.Set("Access-Control-Allow-Headers", headers)
				}
			}
			w.WriteHeader(http.StatusNoContent)
			return
		}
		if ok {
			h := w.Header()
			h.Set("Access-Control-Allow-Origin", origin)
			h.Add("Vary", "Origin")
			h.Set("Access-Control-Expose-Headers", "Content-Disposition")
		}
		next.ServeHTTP(w, r)
	})
}
