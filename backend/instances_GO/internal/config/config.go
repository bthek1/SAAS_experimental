// Package config reads everything the service takes from its environment, with the same
// names and profiles as instances_NET's Config/Settings.cs (and Django's core/settings/
// before it), so `.env` and the deploys need no change.
//
// SETTINGS picks the profile: dev (default), test, e2e, prod or loadtest. The test
// profiles never read `.env` and always trust the published dev key pair (#33); prod and
// loadtest require real keys and tokens, and loadtest refuses public hosts.
package config

import (
	"bufio"
	"fmt"
	"net"
	"net/netip"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// ServiceName is the service's name everywhere outside this folder (#51).
const ServiceName = "instances"

// Settings is the whole configuration of one process.
type Settings struct {
	Profile                   string
	Debug                     bool
	DatabaseURL               string
	DatabasePoolSize          int
	JWTVerifyingKey           string
	InboundPeerToken          string
	OutboundPeerToken         string
	CatalogInternalURL        string
	PeerConnectTimeout        time.Duration
	PeerReadTimeout           time.Duration
	CacheEnabled              bool
	CacheRedisURL             string
	AllowedHosts              []string
	CORSAllowedOrigins        []string
	CORSAllowedOriginPatterns []*regexp.Regexp
	MetricsAllowedNetworks    []netip.Prefix
	HTTPSRedirect             bool
	LoadTest                  bool
}

// IsTestProfile is true for test and e2e.
func (s *Settings) IsTestProfile() bool { return s.Profile == "test" || s.Profile == "e2e" }

// Error is a configuration the service refuses to start with.
type Error struct{ Message string }

func (e *Error) Error() string { return e.Message }

func fail(format string, args ...any) *Error { return &Error{fmt.Sprintf(format, args...)} }

var profiles = []string{"dev", "test", "e2e", "prod", "loadtest"}

// Load reads the process environment and, on dev, prod and loadtest, the repo root's `.env`.
func Load() (*Settings, error) {
	environment := map[string]string{}
	for _, pair := range os.Environ() {
		if key, value, ok := strings.Cut(pair, "="); ok {
			environment[key] = value
		}
	}
	return LoadFrom(environment, findDotEnv())
}

// LoadFrom is Load with the environment and `.env` given, for tests.
func LoadFrom(environment, dotEnv map[string]string) (s *Settings, err error) {
	defer func() {
		// The readers below panic with *Error, so each profile reads as a list.
		if r := recover(); r != nil {
			e, ok := r.(*Error)
			if !ok {
				panic(r)
			}
			s, err = nil, e
		}
	}()
	profile, ok := environment["SETTINGS"]
	if !ok {
		profile = "dev"
	}
	known := false
	for _, p := range profiles {
		known = known || p == profile
	}
	if !known {
		return nil, fail("Unknown SETTINGS value: '%s'. Must be one of %s.", profile, strings.Join(profiles, ", "))
	}
	if profile != "dev" && profile != "prod" && profile != "loadtest" {
		dotEnv = nil
	}
	e := env{environment, dotEnv}
	switch profile {
	case "dev":
		return dev(e), nil
	case "test", "e2e":
		return test(e, profile), nil
	case "prod":
		return prod(e, profile), nil
	default:
		return loadTest(e), nil
	}
}

func common(e env, profile string) *Settings {
	var networks []netip.Prefix
	for _, cidr := range e.list("METRICS_ALLOWED_CIDRS", []string{"127.0.0.1/32", "::1/128"}) {
		prefix, err := netip.ParsePrefix(cidr)
		if err != nil {
			panic(fail("METRICS_ALLOWED_CIDRS: %s is not a network", cidr))
		}
		networks = append(networks, prefix.Masked())
	}
	return &Settings{
		Profile:                profile,
		CatalogInternalURL:     e.str("CATALOG_INTERNAL_URL", "http://localhost:8006"),
		PeerConnectTimeout:     seconds(e.float("PEER_CONNECT_TIMEOUT", 0.5)),
		PeerReadTimeout:        seconds(e.float("PEER_READ_TIMEOUT", 2.0)),
		CacheEnabled:           e.boolean("CACHE_ENABLED", true),
		CacheRedisURL:          e.str("CACHE_REDIS_URL", "redis://localhost:6380/1"),
		MetricsAllowedNetworks: networks,
		DatabasePoolSize:       e.integer("DB_POOL_SIZE", 15),
	}
}

func dev(e env) *Settings {
	s := common(e, "dev")
	s.Debug = true
	s.DatabaseURL = e.str("INSTANCES_DATABASE_URL", "postgres://appuser:apppassword@localhost:5437/instancesdb")
	s.JWTVerifyingKey = orDefault(e.multiline("JWT_VERIFYING_KEY"), DevVerifyingKey)
	s.InboundPeerToken = orDefault(e.str("CATALOG_TO_INSTANCES_TOKEN", ""), "dev-catalog-to-instances")
	s.OutboundPeerToken = orDefault(e.str("INSTANCES_TO_CATALOG_TOKEN", ""), "dev-instances-to-catalog")
	s.AllowedHosts = e.list("ALLOWED_HOSTS", []string{"localhost", "127.0.0.1"})
	s.CORSAllowedOrigins = e.list("CORS_ALLOWED_ORIGINS", []string{"http://localhost:5174"})
	s.CORSAllowedOriginPatterns = []*regexp.Regexp{regexp.MustCompile(`^http://192\.168\.\d+\.\d+:\d+$`)}
	return s
}

func test(e env, profile string) *Settings {
	s := common(e, profile)
	// Postgres only, so even tests name a database: a throwaway one.
	s.DatabaseURL = e.required("INSTANCES_DATABASE_URL")
	// Tests sign with the published pair, whatever a developer's environment says (#33).
	s.JWTVerifyingKey = DevVerifyingKey
	s.InboundPeerToken = "test-catalog-to-instances"
	s.OutboundPeerToken = "test-instances-to-catalog"
	catalog, origins := "http://localhost:8006", []string{}
	if profile == "e2e" {
		catalog, origins = "http://localhost:8016", []string{"http://localhost:5184"}
	}
	s.CatalogInternalURL = e.str("CATALOG_INTERNAL_URL", catalog)
	// Off, so tests see fresh data. Cache tests turn it on themselves.
	s.CacheEnabled = false
	s.AllowedHosts = []string{"localhost", "127.0.0.1"}
	s.CORSAllowedOrigins = e.list("CORS_ALLOWED_ORIGINS", origins)
	return s
}

func prod(e env, profile string) *Settings {
	key := e.multiline("JWT_VERIFYING_KEY")
	if key == "" {
		panic(fail("Set JWT_VERIFYING_KEY."))
	}
	if strings.TrimSpace(key) == strings.TrimSpace(DevVerifyingKey) {
		panic(fail("JWT_VERIFYING_KEY is the published dev key."))
	}
	inbound, outbound := e.str("CATALOG_TO_INSTANCES_TOKEN", ""), e.str("INSTANCES_TO_CATALOG_TOKEN", "")
	if inbound == "" || outbound == "" {
		panic(fail("Set CATALOG_TO_INSTANCES_TOKEN and INSTANCES_TO_CATALOG_TOKEN."))
	}
	s := common(e, profile)
	s.DatabaseURL = e.required("INSTANCES_DATABASE_URL")
	s.JWTVerifyingKey = key
	s.InboundPeerToken = inbound
	s.OutboundPeerToken = outbound
	// No default: the cache fails open, so a wrong URL would otherwise run uncached
	// with no other symptom.
	s.CacheRedisURL = e.required("CACHE_REDIS_URL")
	s.AllowedHosts = e.requiredList("ALLOWED_HOSTS")
	s.CORSAllowedOrigins = e.list("CORS_ALLOWED_ORIGINS", []string{})
	s.HTTPSRedirect = true
	return s
}

// loadTest is prod over plain HTTP for k6 on a private network (#9).
func loadTest(e env) *Settings {
	s := prod(e, "loadtest")
	s.HTTPSRedirect = false
	s.LoadTest = true
	var public []string
	for _, host := range s.AllowedHosts {
		if !IsPrivateHost(host) {
			public = append(public, host)
		}
	}
	if len(public) > 0 {
		panic(fail("SETTINGS=loadtest refuses ALLOWED_HOSTS [%s]: the HTTPS redirect is off here, "+
			"so it only runs behind private addresses", strings.Join(public, ", ")))
	}
	return s
}

var privateSuffixes = []string{".lan", ".internal", ".local", ".localhost"}

// IsPrivateHost is true for a name or address that cannot be reached from the internet.
func IsPrivateHost(host string) bool {
	if host == "localhost" {
		return true
	}
	for _, suffix := range privateSuffixes {
		if strings.HasSuffix(host, suffix) {
			return true
		}
	}
	addr, err := netip.ParseAddr(strings.Trim(host, "[]"))
	if err != nil {
		return false
	}
	addr = addr.Unmap()
	if addr.IsLoopback() {
		return true
	}
	if addr.Is4() {
		b := addr.As4()
		return b[0] == 10 || (b[0] == 172 && b[1] >= 16 && b[1] <= 31) || (b[0] == 192 && b[1] == 168) ||
			(b[0] == 169 && b[1] == 254) || (b[0] == 100 && b[1] >= 64 && b[1] <= 127) || b[0] == 0
	}
	ip := net.IP(addr.AsSlice())
	// Link-local, unique local (fc00::/7) and the old site-local (fec0::/10).
	return ip.IsLinkLocalUnicast() || ip.IsPrivate() || (ip[0] == 0xfe && ip[1]&0xc0 == 0xc0)
}

func seconds(value float64) time.Duration { return time.Duration(value * float64(time.Second)) }

func orDefault(value, fallback string) string {
	if value == "" {
		return fallback
	}
	return value
}

// env reads the environment first, then `.env` (dev, prod and loadtest only).
type env struct{ environment, dotEnv map[string]string }

func (e env) raw(name string) (string, bool) {
	if value, ok := e.environment[name]; ok {
		return value, true
	}
	if e.dotEnv != nil {
		if value, ok := e.dotEnv[name]; ok {
			return value, true
		}
	}
	return "", false
}

func (e env) str(name, fallback string) string {
	if value, ok := e.raw(name); ok {
		return value
	}
	return fallback
}

func (e env) required(name string) string {
	if value, ok := e.raw(name); ok && value != "" {
		return value
	}
	panic(fail("Set %s.", name))
}

// multiline reads a PEM kept on one line with `\n` escapes, as `.env.example` explains.
func (e env) multiline(name string) string {
	value, _ := e.raw(name)
	return strings.ReplaceAll(value, `\n`, "\n")
}

func (e env) list(name string, fallback []string) []string {
	value, ok := e.raw(name)
	if !ok {
		return fallback
	}
	items := []string{}
	for _, item := range strings.Split(value, ",") {
		if item = strings.TrimSpace(item); item != "" {
			items = append(items, item)
		}
	}
	return items
}

func (e env) requiredList(name string) []string {
	if items := e.list(name, nil); len(items) > 0 {
		return items
	}
	panic(fail("Set %s.", name))
}

func (e env) boolean(name string, fallback bool) bool {
	value, ok := e.raw(name)
	if !ok {
		return fallback
	}
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "true", "on", "ok", "y", "yes", "1":
		return true
	}
	return false
}

func (e env) float(name string, fallback float64) float64 {
	value, ok := e.raw(name)
	if !ok || value == "" {
		return fallback
	}
	parsed, err := strconv.ParseFloat(value, 64)
	if err != nil {
		panic(fail("%s: %s is not a number", name, value))
	}
	return parsed
}

func (e env) integer(name string, fallback int) int {
	value, ok := e.raw(name)
	if !ok || value == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		panic(fail("%s: %s is not a whole number", name, value))
	}
	return parsed
}

// findDotEnv reads the repo root's `.env`, found upward from the binary and from the
// working directory. It is absent on a deploy, where env vars come from the unit.
func findDotEnv() map[string]string {
	var starts []string
	if exe, err := os.Executable(); err == nil {
		starts = append(starts, filepath.Dir(exe))
	}
	if wd, err := os.Getwd(); err == nil {
		starts = append(starts, wd)
	}
	for _, start := range starts {
		for dir := start; ; dir = filepath.Dir(dir) {
			candidate := filepath.Join(dir, ".env")
			if isFile(candidate) && isFile(filepath.Join(dir, "AGENTS.md")) {
				if values, err := ParseDotEnv(candidate); err == nil {
					return values
				}
			}
			if filepath.Dir(dir) == dir {
				break
			}
		}
	}
	return nil
}

func isFile(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}

// ParseDotEnv reads KEY=value lines, as instances_NET's DotEnv does.
func ParseDotEnv(path string) (map[string]string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	values := map[string]string{}
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 64*1024), 1024*1024)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		line = strings.TrimLeft(strings.TrimPrefix(line, "export "), " ")
		key, value, ok := strings.Cut(line, "=")
		if !ok || strings.TrimSpace(key) == "" {
			continue
		}
		key, value = strings.TrimSpace(key), strings.TrimSpace(value)
		if len(value) >= 2 && (value[0] == '"' || value[0] == '\'') && value[len(value)-1] == value[0] {
			value = value[1 : len(value)-1]
		}
		values[key] = value
	}
	return values, scanner.Err()
}
