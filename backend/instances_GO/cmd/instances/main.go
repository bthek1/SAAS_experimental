// Command instances is the `instances` service in Go (#52), on the same API, schema and
// env vars as instances_NET. With no arguments it serves HTTP; otherwise the first
// argument is a verb, as `Instances.Api.dll <verb>`: migrate, seed-loadtest, reset-db,
// clear-cache, reconcile-refs, health.
package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	_ "time/tzdata" // IANA zones on any host, as Python's zoneinfo with tzdata.

	"instances/internal/cache"
	"instances/internal/commands"
	"instances/internal/config"
	"instances/internal/server"
	"instances/internal/store"
)

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(args []string) int {
	ctx := context.Background()
	if len(args) > 0 && args[0] == "health" {
		target := "http://127.0.0.1:8000/internal/health/"
		if len(args) > 1 {
			target = args[1]
		}
		return server.HealthCheck(ctx, target)
	}
	settings, err := config.Load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "instances: %s\n", err)
		return 2
	}
	if len(args) > 0 && !strings.HasPrefix(args[0], "-") {
		return command(ctx, args, settings)
	}
	if err := serve(ctx, settings); err != nil {
		fmt.Fprintf(os.Stderr, "instances: %s\n", err)
		return 1
	}
	return 0
}

func serve(ctx context.Context, settings *config.Settings) error {
	address, err := server.ListenAddress(os.Getenv("ASPNETCORE_URLS"))
	if err != nil {
		return err
	}
	app, err := NewApp(ctx, settings)
	if err != nil {
		return err
	}
	defer app.Close()
	httpServer := server.New(settings, address, app.Routes(), app.Auth)

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGTERM, syscall.SIGINT)
	failed := make(chan error, 1)
	go func() { failed <- httpServer.ListenAndServe() }()
	slog.Info("listening", "address", address, "profile", settings.Profile)
	select {
	case err := <-failed:
		if !errors.Is(err, http.ErrServerClosed) {
			return err
		}
	case <-stop:
		shutdown, cancel := context.WithTimeout(ctx, 10*time.Second)
		defer cancel()
		return httpServer.Shutdown(shutdown)
	}
	return nil
}

func command(ctx context.Context, args []string, settings *config.Settings) int {
	switch args[0] {
	case "migrate":
		pool, err := store.Open(ctx, settings.DatabaseURL, 2)
		if err != nil {
			return fail(err)
		}
		defer pool.Close()
		message, err := store.Migrate(ctx, pool)
		if err != nil {
			return fail(err)
		}
		fmt.Println(message)
		return 0
	case "seed-loadtest", "reset-db", "clear-cache":
		if !settings.Debug && !settings.LoadTest {
			fmt.Fprintf(os.Stderr, "instances: %s runs only under dev or loadtest.\n", args[0])
			return 1
		}
		app, err := NewApp(ctx, settings)
		if err != nil {
			return fail(err)
		}
		defer app.Close()
		options := parseOptions(args[1:])
		switch args[0] {
		case "seed-loadtest":
			perOwner, err1 := strconv.Atoi(optionOr(options, "questionnaires-per-owner", "200"))
			seed, err2 := strconv.Atoi(optionOr(options, "seed", "1234"))
			if err1 != nil || err2 != nil {
				return fail(fmt.Errorf("--questionnaires-per-owner and --seed take whole numbers"))
			}
			err = commands.SeedLoadTest(ctx, app.Pool, perOwner, seed, os.Stdout)
		case "reset-db":
			err = commands.ResetDB(ctx, app.Pool, os.Stdout)
		default:
			var redis *cache.RedisStore
			if redis, err = cache.NewRedisStoreWithTimeout(settings.CacheRedisURL, 5*time.Second); err == nil {
				defer redis.Close()
				var removed int64
				if removed, err = redis.Clear(ctx); err == nil {
					fmt.Printf("removed %d keys\n", removed)
				}
			}
		}
		if err != nil {
			return fail(err)
		}
		return 0
	case "reconcile-refs":
		app, err := NewApp(ctx, settings)
		if err != nil {
			return fail(err)
		}
		defer app.Close()
		_, dryRun := parseOptions(args[1:])["dry-run"]
		if err := commands.Reconcile(ctx, app.Refs, dryRun, os.Stdout); err != nil {
			return fail(err)
		}
		return 0
	default:
		fmt.Fprintf(os.Stderr, "instances: unknown command '%s'. Commands: migrate, seed-loadtest, "+
			"reconcile-refs, reset-db, clear-cache, health\n", args[0])
		return 2
	}
}

// parseOptions reads `--name value`, `--name=value`, or a bare `--flag`.
func parseOptions(args []string) map[string]string {
	options := map[string]string{}
	pending := ""
	for _, arg := range args {
		if strings.HasPrefix(arg, "--") {
			if pending != "" {
				options[pending] = ""
			}
			if name, value, ok := strings.Cut(arg[2:], "="); ok {
				options[name], pending = value, ""
			} else {
				pending = arg[2:]
			}
		} else if pending != "" {
			options[pending], pending = arg, ""
		}
	}
	if pending != "" {
		options[pending] = ""
	}
	return options
}

func optionOr(options map[string]string, name, fallback string) string {
	if value, ok := options[name]; ok && value != "" {
		return value
	}
	return fallback
}

func fail(err error) int {
	fmt.Fprintf(os.Stderr, "instances: %s\n", err)
	return 1
}
