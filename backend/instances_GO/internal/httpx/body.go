package httpx

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"unicode/utf8"
)

// Value is one JSON value from a request, kept as its text. A missing field is nil.
type Value json.RawMessage

// Kind is the JSON type: object, array, string, number, true, false or null.
func (v Value) Kind() string {
	trimmed := bytes.TrimLeft(v, " \t\r\n")
	if len(trimmed) == 0 {
		return "null"
	}
	switch trimmed[0] {
	case '{':
		return "object"
	case '[':
		return "array"
	case '"':
		return "string"
	case 't':
		return "true"
	case 'f':
		return "false"
	case 'n':
		return "null"
	}
	return "number"
}

// String is a string value's text.
func (v Value) String() string {
	var text string
	_ = json.Unmarshal(v, &text)
	return text
}

// PythonType is what DRF's messages call the value: `list`, `str`, `int`, `float`, ...
func (v Value) PythonType() string {
	switch v.Kind() {
	case "array":
		return "list"
	case "string":
		return "str"
	case "number":
		if bytes.ContainsAny(v, ".eE") {
			return "float"
		}
		return "int"
	case "true", "false":
		return "bool"
	case "object":
		return "dict"
	}
	return "NoneType"
}

// Object is a request body that is a JSON object: its fields, in order of first use.
type Object map[string]Value

// Field is a field's value, or nil if the body has no such field.
func (o Object) Field(name string) Value {
	if value, ok := o[name]; ok {
		return value
	}
	return nil
}

// ReadValue reads the body as any JSON value; an empty body is `{}`.
func ReadValue(r *http.Request) (Value, error) {
	raw, err := io.ReadAll(r.Body)
	if err != nil {
		return nil, Detail(http.StatusBadRequest, "JSON parse error - "+err.Error())
	}
	if len(raw) == 0 {
		return Value("{}"), nil
	}
	if !json.Valid(raw) {
		var probe any
		message := "invalid JSON"
		if err := json.Unmarshal(raw, &probe); err != nil {
			message = err.Error()
		}
		return nil, Detail(http.StatusBadRequest, "JSON parse error - "+message)
	}
	return Value(bytes.TrimSpace(raw)), nil
}

// ReadObject reads the body as a JSON object; an empty body is `{}`.
func ReadObject(r *http.Request) (Object, error) {
	value, err := ReadValue(r)
	if err != nil {
		return nil, err
	}
	return AsObject(value)
}

// AsObject is the fields of a JSON object, or DRF's 400 for anything else.
func AsObject(value Value) (Object, error) {
	if value.Kind() != "object" {
		return nil, OneFieldError("non_field_errors",
			fmt.Sprintf("Invalid data. Expected a dictionary, but got %s.", objectKind(value)))
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(value, &fields); err != nil {
		return nil, Detail(http.StatusBadRequest, "JSON parse error - "+err.Error())
	}
	object := make(Object, len(fields))
	for name, raw := range fields {
		object[name] = Value(raw)
	}
	return object, nil
}

func objectKind(value Value) string {
	switch value.Kind() {
	case "array":
		return "list"
	case "string":
		return "str"
	case "number":
		return "int"
	case "true", "false":
		return "bool"
	}
	return "NoneType"
}

// Text is a model `CharField(max_length=255, blank=True)`: trimmed, never null. A
// missing field is ("", false).
func Text(value Value, field string, errors *FieldErrors, maxLength int) (string, bool) {
	if value == nil {
		return "", false
	}
	var text string
	switch value.Kind() {
	case "string":
		text = value.String()
	case "number":
		text = string(bytes.TrimSpace(value))
	case "null":
		errors.Add(field, MsgNotNull)
		return "", false
	default:
		errors.Add(field, "Not a valid string.")
		return "", false
	}
	text = strings.TrimSpace(text)
	if utf8.RuneCountInString(text) > maxLength {
		errors.Add(field, fmt.Sprintf("Ensure this field has no more than %d characters.", maxLength))
		return "", false
	}
	return text, true
}

// JSONObject is a `DictField`: any JSON object, kept as its text. A missing field is nil.
func JSONObject(value Value, field string, errors *FieldErrors, required bool) json.RawMessage {
	if value == nil {
		if required {
			errors.Add(field, MsgRequired)
		}
		return nil
	}
	switch value.Kind() {
	case "object":
		return json.RawMessage(bytes.TrimSpace(value))
	case "null":
		errors.Add(field, MsgNotNull)
	default:
		errors.Add(field, fmt.Sprintf("Expected a dictionary of items but got type \"%s\".", value.PythonType()))
	}
	return nil
}

var (
	trueWords  = words("t T y Y yes Yes YES true True TRUE on On ON 1")
	falseWords = words("f F n N no No NO false False FALSE off Off OFF 0")
	nullWords  = words("null Null NULL")
)

func words(text string) map[string]bool {
	set := map[string]bool{}
	for _, word := range strings.Fields(text) {
		set[word] = true
	}
	return set
}

// Boolean is a query string `BooleanField(allow_null=True)`: nil for null or missing.
func Boolean(value *string, field string, errors *FieldErrors) *bool {
	if value == nil || *value == "" || nullWords[*value] {
		return nil
	}
	result := trueWords[*value]
	if !result && !falseWords[*value] {
		errors.Add(field, "Must be a valid boolean.")
		return nil
	}
	return &result
}

// QueryValue is a query parameter, the last of repeated values as Django's QueryDict
// gives it, or nil if absent.
func QueryValue(r *http.Request, name string) *string {
	values, ok := r.URL.Query()[name]
	if !ok || len(values) == 0 {
		return nil
	}
	return &values[len(values)-1]
}
