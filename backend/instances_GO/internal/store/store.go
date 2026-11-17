// Package store opens the database: the `questionnaires_*` tables Django created, which
// instances_NET's EF migrations own (#42). SQL is written by hand and always parameterised.
package store

import (
	"context"
	"fmt"
	"net/url"
	"strings"
	"sync/atomic"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	"instances/internal/httpx"
)

// Open connects a pool to `postgres://user:password@host:port/name`, as the other
// implementations read it: every value UTC, UTF-8 even on the LXC's SQL_ASCII databases.
func Open(ctx context.Context, databaseURL string, poolSize int) (*pgxpool.Pool, error) {
	config, err := Config(databaseURL, poolSize)
	if err != nil {
		return nil, err
	}
	return pgxpool.NewWithConfig(ctx, config)
}

// Config is the pool's configuration, without connecting.
func Config(databaseURL string, poolSize int) (*pgxpool.Config, error) {
	parsed, err := url.Parse(databaseURL)
	if err != nil {
		return nil, fmt.Errorf("INSTANCES_DATABASE_URL: %w", err)
	}
	switch parsed.Scheme {
	case "postgres", "postgresql", "pgsql":
		parsed.Scheme = "postgres"
	default:
		return nil, fmt.Errorf("not a Postgres URL: %s://...", parsed.Scheme)
	}
	// Only sslmode is read from the query, as the other implementations do.
	query := url.Values{}
	if mode := parsed.Query().Get("sslmode"); mode != "" {
		query.Set("sslmode", strings.ToLower(mode))
	}
	parsed.RawQuery = query.Encode()
	config, err := pgxpool.ParseConfig(parsed.String())
	if err != nil {
		return nil, fmt.Errorf("INSTANCES_DATABASE_URL: %w", err)
	}
	config.MaxConns = int32(poolSize)
	config.ConnConfig.RuntimeParams["timezone"] = "UTC"
	config.ConnConfig.RuntimeParams["client_encoding"] = "UTF8"
	config.ConnConfig.Tracer = tracer{}
	return config, nil
}

// Queryer is a pool or a transaction.
type Queryer interface {
	Exec(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error)
	Query(ctx context.Context, sql string, args ...any) (pgx.Rows, error)
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
}

// tracer counts and times every statement for the `db_query*` series, and for any
// counter the request's context carries (the query-count tests).
type tracer struct{}

type startedKey struct{}

type counterKey struct{}

func (tracer) TraceQueryStart(ctx context.Context, _ *pgx.Conn, _ pgx.TraceQueryStartData) context.Context {
	return context.WithValue(ctx, startedKey{}, time.Now())
}

func (tracer) TraceQueryEnd(ctx context.Context, _ *pgx.Conn, _ pgx.TraceQueryEndData) {
	if started, ok := ctx.Value(startedKey{}).(time.Time); ok {
		httpx.ObserveQuery(time.Since(started))
	}
	if counter, ok := ctx.Value(counterKey{}).(*atomic.Int64); ok {
		counter.Add(1)
	}
}

// CountQueries returns a context whose statements are counted into the returned counter.
func CountQueries(ctx context.Context) (context.Context, *atomic.Int64) {
	counter := &atomic.Int64{}
	return context.WithValue(ctx, counterKey{}, counter), counter
}
