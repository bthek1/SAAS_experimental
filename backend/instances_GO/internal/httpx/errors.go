package httpx

import (
	"encoding/json"
	"fmt"
	"net/http"
)

// Messages DRF writes, which the SPA shows as they are.
const (
	MsgRequired         = "This field is required."
	MsgNotNull          = "This field may not be null."
	MsgNotBlank         = "This field may not be blank."
	MsgUnavailable      = "This action is temporarily unavailable. Please try again."
	MsgNotAuthenticated = "Authentication credentials were not provided."
	MsgForbidden        = "You do not have permission to perform this action."
)

// MsgDoesNotExist is a primary key field's message for an id it cannot see.
func MsgDoesNotExist(value string) string {
	return fmt.Sprintf("Invalid pk \"%s\" - object does not exist.", value)
}

// MsgNotAValidUUID is Django's message, curly quotes included.
func MsgNotAValidUUID(value string) string {
	return fmt.Sprintf("“%s” is not a valid UUID.", value)
}

// Error is a response other than success: `{detail}` or `{field: [messages]}`.
type Error struct {
	Status int
	Body   any
}

func (e *Error) Error() string { return fmt.Sprintf("HTTP %d", e.Status) }

// Detail is DRF's `{"detail": message}`.
func Detail(status int, detail string) *Error {
	return &Error{status, map[string]string{"detail": detail}}
}

// NotFound is DRF's 404.
func NotFound() *Error { return Detail(http.StatusNotFound, "Not found.") }

// FieldErrors gathers every bad field, so all are reported at once, as DRF does.
type FieldErrors struct {
	order    []string
	messages map[string][]string
}

// Add records a message for a field.
func (f *FieldErrors) Add(field, message string) {
	if f.messages == nil {
		f.messages = map[string][]string{}
	}
	if _, seen := f.messages[field]; !seen {
		f.order = append(f.order, field)
	}
	f.messages[field] = append(f.messages[field], message)
}

// Has is true if the field has an error.
func (f *FieldErrors) Has(field string) bool { _, ok := f.messages[field]; return ok }

// Err is the 400, or nil if every field was fine.
func (f *FieldErrors) Err() error {
	if len(f.order) == 0 {
		return nil
	}
	return &Error{http.StatusBadRequest, f}
}

// MarshalJSON writes the fields in the order they were found.
func (f *FieldErrors) MarshalJSON() ([]byte, error) {
	out := []byte{'{'}
	for i, field := range f.order {
		if i > 0 {
			out = append(out, ',')
		}
		key, _ := json.Marshal(field)
		value := Encode(f.messages[field])
		out = append(append(append(out, key...), ':'), value...)
	}
	return append(out, '}'), nil
}

// OneFieldError is a 400 for a single field.
func OneFieldError(field, message string) error {
	var errors FieldErrors
	errors.Add(field, message)
	return errors.Err()
}
