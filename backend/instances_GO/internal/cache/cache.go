// Package cache is the server-side cache for expensive reads, with catalog/cache.py's and
// instances_NET's Caching/Cache.cs rules (#11):
//
//   - an owner id is required, so a key cannot be built without a tenant;
//   - a Redis failure is logged and counted, then the value is computed: a cache problem
//     never fails a request;
//   - params come from validated data, never a raw query string;
//   - each owner has a random generation, part of every key; bumping it after a commit
//     makes their entries unreachable without scanning keys.
//
// Values are the response's bytes under a key prefix of this implementation's own
// (`instances-go:`), so it never reads the .NET or Django version's entries.
package cache

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"sync/atomic"
	"time"

	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/redis/go-redis/v9"
)

// KeyPrefix is this implementation's. Not "instances" (Django's pickles) or "instances-net:".
const KeyPrefix = "instances-go:"

// Groups are the fixed groups: each is a Prometheus label.
var Groups = map[string]bool{"dashboard": true, "dashboard-scores": true, "pdf": true}

const generationGroup = "generation"

var requests = promauto.NewCounterVec(prometheus.CounterOpts{
	Name: "app_cache_requests_total", Help: "Cached reads by group and result (hit, miss, error).",
}, []string{"group", "result"})

// ErrMiss is a key with no value.
var ErrMiss = errors.New("cache miss")

// Store is where cached bytes live: Redis in every deploy, a map in tests.
type Store interface {
	Get(ctx context.Context, key string) ([]byte, error)
	Set(ctx context.Context, key string, value []byte, ttl time.Duration) error
	// GetOrAdd is the value at key, storing value first if there is none.
	GetOrAdd(ctx context.Context, key, value string) (string, error)
}

// Cache reads through a Store.
type Cache struct {
	store    Store
	enabled  atomic.Bool
	settings bool
}

// New is a cache that is on when enabled (CACHE_ENABLED).
func New(store Store, enabled bool) *Cache {
	c := &Cache{store: store, settings: enabled}
	c.enabled.Store(true)
	return c
}

// Enabled is CACHE_ENABLED and any test override.
func (c *Cache) Enabled() bool { return c.settings && c.enabled.Load() }

// SetEnabled turns the cache off or back on at run time, for tests.
func (c *Cache) SetEnabled(on bool) { c.enabled.Store(on) }

// Options are a cached read's less common settings.
type Options struct {
	Version      int
	NoGeneration bool
	StoreIf      func([]byte) bool
}

// Cached is the bytes under (group, owner, params), computing and storing them on a miss.
func (c *Cache) Cached(ctx context.Context, group string, owner uuid.UUID, params any, ttl time.Duration,
	compute func() ([]byte, error), options Options) ([]byte, error) {
	if !Groups[group] {
		panic(fmt.Sprintf("unknown cache group '%s': add it to cache.Groups", group))
	}
	if !c.Enabled() {
		return compute()
	}
	version := options.Version
	if version == 0 {
		version = 1
	}
	generation := "none"
	var err error
	if !options.NoGeneration {
		generation, err = c.store.GetOrAdd(ctx, generationKey(owner), newGeneration())
	}
	var key string
	var value []byte
	if err == nil {
		key = EntryKey(group, owner, generation, params, version)
		value, err = c.store.Get(ctx, key)
	}
	if err != nil && !errors.Is(err, ErrMiss) {
		recordError(group, "read", err)
		return compute()
	}
	if err == nil {
		requests.WithLabelValues(group, "hit").Inc()
		return value, nil
	}
	requests.WithLabelValues(group, "miss").Inc()
	value, err = compute()
	if err != nil {
		return nil, err
	}
	if options.StoreIf != nil && !options.StoreIf(value) {
		return value, nil
	}
	if err := c.store.Set(ctx, key, value, ttl); err != nil {
		recordError(group, "write", err)
	}
	return value, nil
}

// BumpOwnerGeneration makes every entry of the owner unreachable. Call it only after the
// transaction that changed the owner's rows has committed.
func (c *Cache) BumpOwnerGeneration(ctx context.Context, owner uuid.UUID) {
	if !c.Enabled() {
		return
	}
	if err := c.store.Set(ctx, generationKey(owner), []byte(newGeneration()), 0); err != nil {
		// The old entries stay valid until their TTL.
		recordError(generationGroup, "bump", err)
	}
}

func generationKey(owner uuid.UUID) string { return "generation:" + owner.String() }

func newGeneration() string {
	return hex.EncodeToString(func() []byte { id := uuid.New(); return id[:] }())
}

// EntryKey is `group:v<version>:<owner>:<generation>:<sha256 of the params' JSON>`.
func EntryKey(group string, owner uuid.UUID, generation string, params any, version int) string {
	encoded, err := json.Marshal(params)
	if err != nil {
		panic(fmt.Sprintf("cache params: %v", err))
	}
	digest := sha256.Sum256(encoded)
	return fmt.Sprintf("%s:v%d:%s:%s:%s", group, version, owner, generation, hex.EncodeToString(digest[:]))
}

func recordError(group, operation string, err error) {
	requests.WithLabelValues(group, "error").Inc()
	slog.Warn("cache failed", "operation", operation, "group", group, "error", err)
}

// RedisStore is Redis, failing fast: the timeouts bound how long a failing Redis can hold
// up a request, and a Redis that is down at start-up is only a miss.
type RedisStore struct{ client *redis.Client }

// NewRedisStore reads `redis://[user:password@]host:port/db`, with request-path timeouts.
func NewRedisStore(rawURL string) (*RedisStore, error) {
	return NewRedisStoreWithTimeout(rawURL, 100*time.Millisecond)
}

// NewRedisStoreWithTimeout is NewRedisStore with other timeouts, for commands.
func NewRedisStoreWithTimeout(rawURL string, timeout time.Duration) (*RedisStore, error) {
	options, err := redis.ParseURL(rawURL)
	if err != nil {
		return nil, fmt.Errorf("CACHE_REDIS_URL: %w", err)
	}
	options.DialTimeout = timeout
	options.ReadTimeout = timeout
	options.WriteTimeout = timeout
	options.MaxRetries = -1
	options.DisableIdentity = true
	return &RedisStore{client: redis.NewClient(options)}, nil
}

// Get reads one key.
func (r *RedisStore) Get(ctx context.Context, key string) ([]byte, error) {
	value, err := r.client.Get(ctx, KeyPrefix+key).Bytes()
	if errors.Is(err, redis.Nil) {
		return nil, ErrMiss
	}
	return value, err
}

// Set writes one key; a zero ttl keeps it.
func (r *RedisStore) Set(ctx context.Context, key string, value []byte, ttl time.Duration) error {
	return r.client.Set(ctx, KeyPrefix+key, value, ttl).Err()
}

// GetOrAdd stores value if the key has none, then reads what is there.
func (r *RedisStore) GetOrAdd(ctx context.Context, key, value string) (string, error) {
	if err := r.client.SetNX(ctx, KeyPrefix+key, value, 0).Err(); err != nil {
		return "", err
	}
	stored, err := r.client.Get(ctx, KeyPrefix+key).Result()
	if errors.Is(err, redis.Nil) {
		return value, nil
	}
	return stored, err
}

// Clear removes every key under this implementation's prefix, for `clear-cache` between
// load-test runs: never catalog's or another implementation's. Not for request paths.
func (r *RedisStore) Clear(ctx context.Context) (int64, error) {
	var removed int64
	iterator := r.client.Scan(ctx, 0, KeyPrefix+"*", 1000).Iterator()
	for iterator.Next(ctx) {
		n, err := r.client.Del(ctx, iterator.Val()).Result()
		if err != nil {
			return removed, err
		}
		removed += n
	}
	return removed, iterator.Err()
}

// Close releases the connections.
func (r *RedisStore) Close() error { return r.client.Close() }
