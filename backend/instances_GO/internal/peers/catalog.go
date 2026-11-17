// Package peers reaches `catalog`'s `/internal/` over HTTP (#13), with short timeouts, so
// a dead peer never holds a request long. Shapes: backend/contracts/response.*.json.
package peers

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// Unavailable is a peer with no usable answer: down, too slow, 5xx, or it refused our token.
type Unavailable struct{ Message string }

func (u *Unavailable) Error() string { return "catalog unavailable: " + u.Message }

// IsUnavailable is true for an *Unavailable anywhere in the chain.
func IsUnavailable(err error) bool {
	var u *Unavailable
	return errors.As(err, &u)
}

// Catalog is what this service asks of `catalog`. Tests swap in a fake.
type Catalog interface {
	// Fetch is catalog's snapshot of a type, or nil if it has no such type.
	Fetch(ctx context.Context, kind string, id string) (json.RawMessage, error)
	// Snapshots calls each with every snapshot of one kind, page after page.
	Snapshots(ctx context.Context, kind string, each func(json.RawMessage) error) error
}

var slugs = map[string]string{"questionnaire_type": "questionnaire-types", "battery_type": "battery-types"}

// HTTPCatalog is Catalog over HTTP.
type HTTPCatalog struct {
	base   string
	token  string
	client *http.Client
}

// NewHTTPCatalog connects within connectTimeout and gives up on a whole call after
// connectTimeout + readTimeout, as instances_NET's HttpCatalogClient does.
func NewHTTPCatalog(baseURL, token string, connectTimeout, readTimeout time.Duration) *HTTPCatalog {
	transport := &http.Transport{
		DialContext:     (&net.Dialer{Timeout: connectTimeout}).DialContext,
		IdleConnTimeout: 30 * time.Second,
		MaxIdleConns:    32,
	}
	return &HTTPCatalog{
		base:   strings.TrimRight(baseURL, "/") + "/",
		token:  token,
		client: &http.Client{Transport: transport, Timeout: connectTimeout + readTimeout},
	}
}

// Fetch asks for one snapshot.
func (c *HTTPCatalog) Fetch(ctx context.Context, kind, id string) (json.RawMessage, error) {
	status, body, err := c.get(ctx, fmt.Sprintf("internal/%s/%s/", slugs[kind], id))
	if err != nil {
		return nil, err
	}
	if status == http.StatusNotFound {
		return nil, nil
	}
	if status != http.StatusOK {
		return nil, &Unavailable{fmt.Sprintf("fetch: HTTP %d", status)}
	}
	if !json.Valid(body) {
		return nil, &Unavailable{"unreadable answer"}
	}
	return body, nil
}

// Snapshots pages through `?after=`.
func (c *HTTPCatalog) Snapshots(ctx context.Context, kind string, each func(json.RawMessage) error) error {
	after := ""
	for {
		path := fmt.Sprintf("internal/%s/", slugs[kind])
		if after != "" {
			path += "?after=" + url.QueryEscape(after)
		}
		status, body, err := c.get(ctx, path)
		if err != nil {
			return err
		}
		if status != http.StatusOK {
			return &Unavailable{fmt.Sprintf("list: HTTP %d", status)}
		}
		var page struct {
			Results []json.RawMessage `json:"results"`
			Next    *string           `json:"next"`
		}
		if err := json.Unmarshal(body, &page); err != nil {
			return &Unavailable{"unreadable answer: " + err.Error()}
		}
		for _, snapshot := range page.Results {
			if err := each(snapshot); err != nil {
				return err
			}
		}
		if page.Next == nil {
			return nil
		}
		after = *page.Next
	}
}

func (c *HTTPCatalog) get(ctx context.Context, path string) (int, []byte, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, c.base+path, nil)
	if err != nil {
		return 0, nil, &Unavailable{err.Error()}
	}
	request.Header.Set("Authorization", "Bearer "+c.token)
	response, err := c.client.Do(request)
	if err != nil {
		return 0, nil, &Unavailable{fmt.Sprintf("GET /%s: %v", path, err)}
	}
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		return 0, nil, &Unavailable{fmt.Sprintf("GET /%s: %v", path, err)}
	}
	status := response.StatusCode
	// A refused token is a deployment fault, and retrying can recover from that.
	if status >= 500 || status == http.StatusUnauthorized || status == http.StatusForbidden {
		return 0, nil, &Unavailable{fmt.Sprintf("GET /%s: HTTP %d", path, status)}
	}
	return status, body, nil
}
