package config_test

import (
	"os"
	"regexp"
	"strings"
	"testing"

	"instances/internal/config"
)

func load(t *testing.T, environment map[string]string, dotEnv map[string]string) (*config.Settings, error) {
	t.Helper()
	return config.LoadFrom(environment, dotEnv)
}

func TestDevIsTheDefaultAndReadsDotEnv(t *testing.T) {
	s, err := load(t, map[string]string{}, map[string]string{"INSTANCES_DATABASE_URL": "postgres://x/from-file"})
	if err != nil {
		t.Fatal(err)
	}
	if s.Profile != "dev" || !s.Debug || s.DatabaseURL != "postgres://x/from-file" {
		t.Fatalf("%+v", s)
	}
	if s.JWTVerifyingKey != config.DevVerifyingKey || s.InboundPeerToken != "dev-catalog-to-instances" {
		t.Fatal("dev should fall back to the dev key and tokens")
	}
}

func TestTestProfilesNeverReadDotEnvAndTrustTheDevKey(t *testing.T) {
	s, err := load(t,
		map[string]string{"SETTINGS": "test", "INSTANCES_DATABASE_URL": "postgres://x/t", "JWT_VERIFYING_KEY": "other"},
		map[string]string{"CACHE_ENABLED": "true", "CATALOG_INTERNAL_URL": "http://from-file"})
	if err != nil {
		t.Fatal(err)
	}
	if s.JWTVerifyingKey != config.DevVerifyingKey || s.CacheEnabled || s.CatalogInternalURL != "http://localhost:8006" {
		t.Fatalf("%+v", s)
	}
	if s.InboundPeerToken != "test-catalog-to-instances" || s.OutboundPeerToken != "test-instances-to-catalog" {
		t.Fatal("test tokens")
	}
	if _, err := load(t, map[string]string{"SETTINGS": "test"}, nil); err == nil ||
		err.Error() != "Set INSTANCES_DATABASE_URL." {
		t.Fatalf("test without a database: %v", err)
	}
}

func prodEnv() map[string]string {
	return map[string]string{
		"SETTINGS": "prod", "INSTANCES_DATABASE_URL": "postgres://x/p", "JWT_VERIFYING_KEY": "-----BEGIN PUBLIC KEY-----\\nreal",
		"CATALOG_TO_INSTANCES_TOKEN": "in", "INSTANCES_TO_CATALOG_TOKEN": "out",
		"CACHE_REDIS_URL": "redis://c/1", "ALLOWED_HOSTS": "api.example.com",
	}
}

func TestProdRequiresItsSecretsAndRefusesTheDevKey(t *testing.T) {
	s, err := load(t, prodEnv(), nil)
	if err != nil {
		t.Fatal(err)
	}
	if !s.HTTPSRedirect || s.JWTVerifyingKey != "-----BEGIN PUBLIC KEY-----\nreal" {
		t.Fatalf("%+v", s)
	}
	for name, message := range map[string]string{
		"JWT_VERIFYING_KEY":          "Set JWT_VERIFYING_KEY.",
		"CATALOG_TO_INSTANCES_TOKEN": "Set CATALOG_TO_INSTANCES_TOKEN and INSTANCES_TO_CATALOG_TOKEN.",
		"CACHE_REDIS_URL":            "Set CACHE_REDIS_URL.",
		"ALLOWED_HOSTS":              "Set ALLOWED_HOSTS.",
	} {
		env := prodEnv()
		delete(env, name)
		if _, err := load(t, env, nil); err == nil || err.Error() != message {
			t.Errorf("without %s: %v", name, err)
		}
	}
	env := prodEnv()
	env["JWT_VERIFYING_KEY"] = strings.ReplaceAll(config.DevVerifyingKey, "\n", `\n`)
	if _, err := load(t, env, nil); err == nil || !strings.Contains(err.Error(), "published dev key") {
		t.Fatalf("dev key in prod: %v", err)
	}
}

func TestLoadTestRefusesPublicHosts(t *testing.T) {
	env := prodEnv()
	env["SETTINGS"] = "loadtest"
	env["ALLOWED_HOSTS"] = "192.168.2.247,instances.loadtest.internal"
	s, err := load(t, env, nil)
	if err != nil || s.HTTPSRedirect || !s.LoadTest {
		t.Fatalf("%+v %v", s, err)
	}
	env["ALLOWED_HOSTS"] = "192.168.2.247,api.example.com"
	if _, err := load(t, env, nil); err == nil || !strings.Contains(err.Error(), "api.example.com") {
		t.Fatalf("public host: %v", err)
	}
}

func TestUnknownProfile(t *testing.T) {
	if _, err := load(t, map[string]string{"SETTINGS": "parity"}, nil); err == nil {
		t.Fatal("parity is catalog's profile, not this service's")
	}
}

func TestPrivateHosts(t *testing.T) {
	for host, private := range map[string]bool{
		"localhost": true, "x.internal": true, "10.1.2.3": true, "172.16.0.1": true, "172.32.0.1": false,
		"192.168.2.70": true, "100.64.0.1": true, "8.8.8.8": false, "[::1]": true, "fd00::1": true,
		"2001:db8::1": false, "example.com": false,
	} {
		if config.IsPrivateHost(host) != private {
			t.Errorf("%s: want private=%v", host, private)
		}
	}
}

// The Go copy of the dev key must be the one in common/dev_keys.py.
func TestDevKeyMatchesThePythonFile(t *testing.T) {
	source, err := os.ReadFile("../../../common/common/dev_keys.py")
	if err != nil {
		t.Fatal(err)
	}
	match := regexp.MustCompile(`(?s)-----BEGIN PUBLIC KEY-----.*?-----END PUBLIC KEY-----`).Find(source)
	if strings.TrimSpace(string(match)) != strings.TrimSpace(config.DevVerifyingKey) {
		t.Fatal("DevVerifyingKey differs from common/dev_keys.py")
	}
}
