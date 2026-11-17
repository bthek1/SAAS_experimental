// Package testdb starts a throwaway Postgres in Docker for tests, as the Python suites
// do (backend/parity_instances/conftest.py): on a free port, its data in tmpfs, gone when
// the test binary's tests finish. Tests skip when Docker is missing.
package testdb

import (
	"context"
	"fmt"
	"os/exec"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"instances/internal/store"
)

const image = "postgres:16-alpine"

// Server is one Postgres container; each test makes its own database in it.
type Server struct {
	name, base string
}

var (
	once    sync.Once
	shared  *Server
	failure error
)

// Start returns the package's container, starting it on first use.
func Start(t testing.TB) *Server {
	t.Helper()
	if _, err := exec.LookPath("docker"); err != nil {
		t.Skip("needs Docker")
	}
	once.Do(func() { shared, failure = start() })
	if failure != nil {
		t.Fatalf("throwaway Postgres: %v", failure)
	}
	return shared
}

func start() (*Server, error) {
	name := "instances-go-test-" + uuid.NewString()[:8]
	if out, err := exec.Command("docker", "run", "--rm", "-d", "--name", name,
		"--tmpfs", "/var/lib/postgresql/data", "-e", "POSTGRES_PASSWORD=throwaway",
		"-p", "127.0.0.1::5432", image).CombinedOutput(); err != nil {
		return nil, fmt.Errorf("docker run: %v: %s", err, out)
	}
	out, err := exec.Command("docker", "port", name, "5432/tcp").Output()
	if err != nil {
		Stop(&Server{name: name})
		return nil, err
	}
	port := strings.TrimSpace(strings.Split(string(out), "\n")[0])
	port = port[strings.LastIndex(port, ":")+1:]
	for range 120 {
		ready := exec.Command("docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-q")
		if ready.Run() == nil {
			break
		}
		time.Sleep(500 * time.Millisecond)
	}
	return &Server{name: name, base: "postgres://postgres:throwaway@127.0.0.1:" + port}, nil
}

// Stop removes the container. Call it from TestMain.
func Stop(s *Server) {
	if s != nil {
		_ = exec.Command("docker", "rm", "-f", s.name).Run()
	}
}

// StopShared removes the package's container, if one was started.
func StopShared() { Stop(shared) }

// Name is the container's name, for `docker exec`.
func (s *Server) Name() string { return s.name }

// Database creates an empty database and returns its URL.
func (s *Server) Database(t testing.TB) string {
	t.Helper()
	name := "t_" + strings.ReplaceAll(uuid.NewString(), "-", "")[:16]
	if out, err := exec.Command("docker", "exec", s.name, "psql", "-U", "postgres", "-qc",
		"CREATE DATABASE "+name).CombinedOutput(); err != nil {
		t.Fatalf("create database: %v: %s", err, out)
	}
	return s.base + "/" + name
}

// Migrated creates a database at the baseline and returns a pool on it.
func (s *Server) Migrated(t testing.TB) (*pgxpool.Pool, string) {
	t.Helper()
	url := s.Database(t)
	pool, err := store.Open(context.Background(), url, 10)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(pool.Close)
	if _, err := store.Migrate(context.Background(), pool); err != nil {
		t.Fatal(err)
	}
	return pool, url
}
