package main

import (
	"context"
	"net/http"

	"github.com/jackc/pgx/v5/pgxpool"

	"instances/internal/api"
	"instances/internal/cache"
	"instances/internal/config"
	"instances/internal/dashboard"
	"instances/internal/peers"
	"instances/internal/refs"
	"instances/internal/server"
	"instances/internal/store"
)

// App holds what every handler shares.
type App struct {
	Settings *config.Settings
	Pool     *pgxpool.Pool
	Auth     *server.Auth
	Redis    *cache.RedisStore
	Cache    *cache.Cache
	Catalog  peers.Catalog
	Refs     *refs.Service
	Handlers *api.Handlers
}

// NewApp opens the pool and the cache. Nothing connects until it is first used.
func NewApp(ctx context.Context, settings *config.Settings) (*App, error) {
	pool, err := store.Open(ctx, settings.DatabaseURL, settings.DatabasePoolSize)
	if err != nil {
		return nil, err
	}
	auth, err := server.NewAuth(settings.JWTVerifyingKey, pool)
	if err != nil {
		pool.Close()
		return nil, err
	}
	redis, err := cache.NewRedisStore(settings.CacheRedisURL)
	if err != nil {
		pool.Close()
		return nil, err
	}
	c := cache.New(redis, settings.CacheEnabled)
	catalog := peers.NewHTTPCatalog(settings.CatalogInternalURL, settings.OutboundPeerToken,
		settings.PeerConnectTimeout, settings.PeerReadTimeout)
	service := &refs.Service{Pool: pool, Cache: c, Catalog: catalog}
	return &App{
		Settings: settings, Pool: pool, Auth: auth, Redis: redis, Cache: c, Catalog: catalog, Refs: service,
		Handlers: &api.Handlers{Settings: settings, Pool: pool, Refs: service, Cache: c,
			Dashboard: &dashboard.Service{Pool: pool}},
	}, nil
}

// Close releases the pool and Redis.
func (a *App) Close() {
	a.Pool.Close()
	_ = a.Redis.Close()
}

// Routes is every endpoint, with instances_NET's controllers' templates (the `view` label).
func (a *App) Routes() []*server.Route {
	h := a.Handlers
	get, post, patch, del := http.MethodGet, http.MethodPost, http.MethodPatch, http.MethodDelete
	return []*server.Route{
		{Method: get, Template: "api/questionnaires", Access: server.Owner, Handle: h.ListQuestionnaires},
		{Method: post, Template: "api/questionnaires", Access: server.Owner, Handle: h.CreateQuestionnaire},
		{Method: get, Template: "api/questionnaires/{id}", Access: server.Owner, Handle: h.GetQuestionnaire},
		{Method: patch, Template: "api/questionnaires/{id}", Access: server.Owner, Handle: h.UpdateQuestionnaire},
		{Method: del, Template: "api/questionnaires/{id}", Access: server.Owner, Handle: h.DeleteQuestionnaire},
		{Method: get, Template: "api/questionnaires/{id}/pdf", Access: server.Owner, Handle: h.PDF},
		{Method: get, Template: "api/questionnaires/by-token/{shareToken}", Access: server.Anyone,
			Handle: h.ReadQuestionnaireByToken},
		{Method: patch, Template: "api/questionnaires/by-token/{shareToken}/submit", Access: server.Anyone,
			Handle: h.SubmitByToken},

		{Method: get, Template: "api/batteries", Access: server.Owner, Handle: h.ListBatteries},
		{Method: post, Template: "api/batteries", Access: server.Owner, Handle: h.CreateBattery},
		{Method: get, Template: "api/batteries/{id}", Access: server.Owner, Handle: h.GetBattery},
		{Method: del, Template: "api/batteries/{id}", Access: server.Owner, Handle: h.DeleteBattery},
		{Method: get, Template: "api/batteries/by-token/{shareToken}", Access: server.Anyone,
			Handle: h.ReadBatteryByToken},

		{Method: get, Template: "api/dashboard", Access: server.Owner, Handle: h.Summary},
		{Method: get, Template: "api/dashboard/scores", Access: server.Owner, Handle: h.Scores},

		{Method: post, Template: "internal/events", Access: server.Peer, Handle: h.Event},
		{Method: post, Template: "internal/refs/{kind}/{refId:guid}/retire", Access: server.Peer, Handle: h.Retire},
		{Method: get, Template: "internal/health", Access: server.Anyone, Handle: server.Health},
	}
}
