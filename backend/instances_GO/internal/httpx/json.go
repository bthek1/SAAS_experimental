// Package httpx is the wire format the SPA, respondents and `catalog` read: DRF's error
// shapes, pagination and timestamps, as instances_NET's Http/ folder writes them. Change
// any of it only with a parity test (backend/parity_instances/).
package httpx

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"time"
)

// Time is a UTC instant, written as Python's `isoformat()` with DRF's `Z`: microseconds
// only when there are any.
type Time struct{ time.Time }

// Now is the current time to the microsecond Postgres keeps, so a response shows what
// was stored.
func Now() time.Time { return time.Now().UTC().Truncate(time.Microsecond) }

// Format writes an instant as `isoformat()`: `Z` for a zero offset, `+hh:mm` otherwise.
func Format(t time.Time) string {
	text := t.Format("2006-01-02T15:04:05")
	if micros := t.Nanosecond() / 1000; micros != 0 {
		text += fmt.Sprintf(".%06d", micros)
	}
	_, offset := t.Zone()
	if offset == 0 {
		return text + "Z"
	}
	sign := "+"
	if offset < 0 {
		sign, offset = "-", -offset
	}
	return fmt.Sprintf("%s%s%02d:%02d", text, sign, offset/3600, offset%3600/60)
}

// MarshalJSON writes the instant in UTC.
func (t Time) MarshalJSON() ([]byte, error) {
	return []byte(strconv.Quote(Format(t.UTC()))), nil
}

// Zoned is an instant written in its own zone's offset (the dashboard's `range`).
type Zoned struct{ time.Time }

// MarshalJSON writes the instant with its offset.
func (t Zoned) MarshalJSON() ([]byte, error) { return []byte(strconv.Quote(Format(t.Time))), nil }

// Date is a calendar day, `yyyy-mm-dd`.
type Date struct{ time.Time }

// MarshalJSON writes the day.
func (d Date) MarshalJSON() ([]byte, error) {
	return []byte(strconv.Quote(d.Format("2006-01-02"))), nil
}

// Encode is JSON as DRF wrote it: no HTML escaping, stored JSON passed through.
func Encode(value any) []byte {
	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(value); err != nil {
		panic(fmt.Sprintf("httpx: cannot encode %T: %v", value, err))
	}
	return bytes.TrimSuffix(buffer.Bytes(), []byte("\n"))
}

// WriteJSON sends a status and a body. A nil body sends no content.
func WriteJSON(w http.ResponseWriter, status int, body any) {
	if body == nil {
		w.WriteHeader(status)
		return
	}
	WriteBytes(w, status, Encode(body))
}

// WriteBytes sends JSON already encoded (a cached body).
func WriteBytes(w http.ResponseWriter, status int, encoded []byte) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Content-Length", strconv.Itoa(len(encoded)))
	w.WriteHeader(status)
	_, _ = w.Write(encoded)
}
