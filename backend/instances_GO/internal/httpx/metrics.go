package httpx

import (
	"net"
	"net/http"
	"net/netip"
	"strconv"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// LatencyBuckets are the Django version's (django-prometheus), as catalog/db.py and
// instances_NET's RequestMetrics.cs copy them, so every run lines up (#44).
var LatencyBuckets = []float64{0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0, 25.0, 50.0, 75.0}

// Request and DB series with catalog's names, labels and buckets. Requests carry the
// route template as `view`, never the URL, so ids never become label values.
var (
	requests = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "http_requests_total", Help: "Requests by route template, method and status.",
	}, []string{"view", "method", "status"})
	latency = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name: "http_request_duration_seconds", Help: "Request latency by route template and method.",
		Buckets: LatencyBuckets,
	}, []string{"view", "method"})
	queries = promauto.NewCounter(prometheus.CounterOpts{
		Name: "db_queries_total", Help: "SQL statements executed.",
	})
	queryLatency = promauto.NewHistogram(prometheus.HistogramOpts{
		Name: "db_query_duration_seconds", Help: "SQL statement latency.", Buckets: LatencyBuckets,
	})
)

// ObserveQuery records one SQL statement.
func ObserveQuery(elapsed time.Duration) {
	queries.Inc()
	queryLatency.Observe(elapsed.Seconds())
}

// StatusRecorder remembers the status a handler wrote.
type StatusRecorder struct {
	http.ResponseWriter
	Status int
}

// WriteHeader records the status.
func (s *StatusRecorder) WriteHeader(status int) {
	if s.Status == 0 {
		s.Status = status
	}
	s.ResponseWriter.WriteHeader(status)
}

func (s *StatusRecorder) Write(b []byte) (int, error) {
	if s.Status == 0 {
		s.Status = http.StatusOK
	}
	return s.ResponseWriter.Write(b)
}

// Unwrap lets http.ResponseController reach the connection.
func (s *StatusRecorder) Unwrap() http.ResponseWriter { return s.ResponseWriter }

// ObserveRequest records one request under its route template.
func ObserveRequest(view, method string, status int, elapsed time.Duration) {
	if status == 0 {
		status = http.StatusOK
	}
	requests.WithLabelValues(view, method, strconv.Itoa(status)).Inc()
	latency.WithLabelValues(view, method).Observe(elapsed.Seconds())
}

var forwardingHeaders = []string{"X-Forwarded-For", "X-Real-IP", "Forwarded"}

// MetricsEndpoint answers `/metrics` for the scraper only (#9), ahead of host filtering
// and routing, since Prometheus scrapes by IP over plain HTTP. Only a direct peer inside
// METRICS_ALLOWED_CIDRS, never a request through a proxy (any forwarding header), so a
// proxy in front can never make it public. Everyone else gets an unknown path's 404.
func MetricsEndpoint(allowed []netip.Prefix, next http.Handler) http.Handler {
	exporter := promhttp.Handler()
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.TrimRight(r.URL.Path, "/") != "/metrics" {
			next.ServeHTTP(w, r)
			return
		}
		if r.Method != http.MethodGet || !scrapeAllowed(r, allowed) {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		exporter.ServeHTTP(w, r)
	})
}

func scrapeAllowed(r *http.Request, allowed []netip.Prefix) bool {
	for _, header := range forwardingHeaders {
		if _, present := r.Header[http.CanonicalHeaderKey(header)]; present {
			return false
		}
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return false
	}
	peer, err := netip.ParseAddr(host)
	if err != nil {
		return false
	}
	peer = peer.Unmap().WithZone("")
	for _, network := range allowed {
		if network.Contains(peer) {
			return true
		}
	}
	return false
}
