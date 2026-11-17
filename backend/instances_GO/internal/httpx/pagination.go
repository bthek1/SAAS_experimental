package httpx

import (
	"net/http"
	"sort"
	"strconv"
	"strings"
)

// Page sizes, as common.pagination.StandardPagination set them (#10).
const (
	DefaultPageSize = 25
	MaxPageSize     = 100
)

// Page is DRF's `{count, next, previous, results}`.
type Page[T any] struct {
	Count    int     `json:"count"`
	Next     *string `json:"next"`
	Previous *string `json:"previous"`
	Results  []T     `json:"results"`
}

// Pagination is `?page=` and `?page_size=` (default 25, at most 100).
type Pagination struct{ Number, Size int }

// Skip is how many rows come before this page.
func (p Pagination) Skip() int { return (p.Number - 1) * p.Size }

// PaginationFrom reads the query. A page that cannot exist is checked in BuildPage.
func PaginationFrom(r *http.Request) (Pagination, error) {
	query := r.URL.Query()
	size := DefaultPageSize
	if raw, ok := query["page_size"]; ok && len(raw) > 0 {
		if parsed, err := strconv.Atoi(strings.TrimSpace(raw[0])); err == nil && parsed > 0 {
			size = min(parsed, MaxPageSize)
		}
	}
	number := 1
	if raw, ok := query["page"]; ok && len(raw) > 0 {
		parsed, err := strconv.Atoi(strings.TrimSpace(raw[0]))
		// Not a positive number: Django's paginator says "Invalid page".
		if err != nil || parsed < 1 {
			return Pagination{}, Detail(http.StatusNotFound, "Invalid page.")
		}
		number = parsed
	}
	return Pagination{number, size}, nil
}

// BuildPage wraps one page of results, with absolute links on the request's own host.
func BuildPage[T any](r *http.Request, p Pagination, count int, results []T) (*Page[T], error) {
	pages := max(1, (count+p.Size-1)/p.Size)
	if p.Number > pages {
		return nil, Detail(http.StatusNotFound, "Invalid page.")
	}
	page := &Page[T]{Count: count, Results: results}
	if results == nil {
		page.Results = []T{}
	}
	if p.Number < pages {
		next := link(r, p.Number+1)
		page.Next = &next
	}
	if p.Number > 1 {
		previous := link(r, p.Number-1)
		page.Previous = &previous
	}
	return page, nil
}

// link is DRF's replace_query_param, or remove_query_param for page 1: keys sorted.
func link(r *http.Request, page int) string {
	query := r.URL.Query()
	if page == 1 {
		delete(query, "page")
	} else {
		query["page"] = []string{strconv.Itoa(page)}
	}
	keys := make([]string, 0, len(query))
	for key := range query {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	var b strings.Builder
	if r.TLS != nil {
		b.WriteString("https://")
	} else {
		b.WriteString("http://")
	}
	b.WriteString(r.Host)
	b.WriteString(r.URL.Path)
	first := true
	for _, key := range keys {
		for _, value := range query[key] {
			if first {
				b.WriteByte('?')
				first = false
			} else {
				b.WriteByte('&')
			}
			b.WriteString(QuotePlus(key))
			b.WriteByte('=')
			b.WriteString(QuotePlus(value))
		}
	}
	return b.String()
}

// QuotePlus is Python's `urllib.parse.quote_plus`.
func QuotePlus(value string) string {
	var b strings.Builder
	for i := 0; i < len(value); i++ {
		c := value[i]
		switch {
		case 'A' <= c && c <= 'Z', 'a' <= c && c <= 'z', '0' <= c && c <= '9', c == '_', c == '.', c == '-', c == '~':
			b.WriteByte(c)
		case c == ' ':
			b.WriteByte('+')
		default:
			b.WriteString("%" + strings.ToUpper(strconv.FormatInt(int64(c)>>4, 16)) +
				strings.ToUpper(strconv.FormatInt(int64(c)&15, 16)))
		}
	}
	return b.String()
}
