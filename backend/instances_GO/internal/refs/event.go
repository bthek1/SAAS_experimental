package refs

import (
	"bytes"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
)

// Kinds of copy.
const (
	QuestionnaireType = "questionnaire_type"
	BatteryType       = "battery_type"
)

// IsKnown is true for the two kinds of copy.
func IsKnown(kind string) bool { return kind == QuestionnaireType || kind == BatteryType }

// BadEvent is a malformed event: retrying cannot help, so it is a 400, not a 5xx.
type BadEvent struct{ Message string }

func (b *BadEvent) Error() string { return b.Message }

func bad(format string, args ...any) *BadEvent { return &BadEvent{fmt.Sprintf(format, args...)} }

// element is one JSON value, kept as its text.
type element json.RawMessage

func (e element) kind() string {
	trimmed := bytes.TrimLeft(e, " \t\r\n")
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
	case 't', 'f':
		return "bool"
	case 'n':
		return "null"
	}
	return "number"
}

// field is a member of an object; anything missing, or a non-object, is a BadEvent.
func (e element) field(name string) (element, error) {
	if e.kind() != "object" {
		return nil, bad("'%s'", name)
	}
	var members map[string]json.RawMessage
	if err := json.Unmarshal(e, &members); err != nil {
		return nil, bad("'%s'", name)
	}
	value, ok := members[name]
	if !ok {
		return nil, bad("'%s'", name)
	}
	return element(value), nil
}

func (e element) text(name string) (string, error) {
	value, err := e.field(name)
	if err != nil {
		return "", err
	}
	if value.kind() != "string" {
		return "", bad("'%s' is not text", name)
	}
	var text string
	_ = json.Unmarshal(value, &text)
	return text, nil
}

func (e element) uuid(name string) (uuid.UUID, error) {
	value, err := e.field(name)
	if err != nil {
		return uuid.UUID{}, err
	}
	var text string
	if value.kind() != "string" || json.Unmarshal(value, &text) != nil {
		return uuid.UUID{}, bad("'%s' is not a UUID", name)
	}
	id, ok := parseLenient(text)
	if !ok {
		return uuid.UUID{}, bad("'%s' is not a UUID", name)
	}
	return id, nil
}

// parseLenient is .NET's Guid.TryParse: hex, dashed, or in braces or parentheses.
func parseLenient(text string) (uuid.UUID, bool) {
	trimmed := strings.TrimSpace(text)
	if len(trimmed) == 38 && ((trimmed[0] == '{' && trimmed[37] == '}') || (trimmed[0] == '(' && trimmed[37] == ')')) {
		trimmed = trimmed[1:37]
	}
	if len(trimmed) != 32 && len(trimmed) != 36 {
		return uuid.UUID{}, false
	}
	id, err := uuid.Parse(trimmed)
	return id, err == nil
}

// event is an event's or a snapshot's envelope.
type event struct {
	body               element
	Type, Kind, Action string
}

func parseEvent(body json.RawMessage) (*event, error) {
	root := element(body)
	if root.kind() != "object" {
		return nil, bad("an event is a JSON object")
	}
	value, err := root.field("type")
	if err != nil {
		return nil, err
	}
	var typeName string
	if value.kind() != "string" || json.Unmarshal(value, &typeName) != nil {
		return nil, bad("'type' is not a string")
	}
	e := &event{body: root, Type: typeName, Action: typeName}
	if dot := strings.LastIndex(typeName, "."); dot >= 0 {
		e.Kind, e.Action = typeName[:dot], typeName[dot+1:]
	}
	return e, nil
}

func (e *event) aggregateID() (uuid.UUID, error) { return e.body.uuid("aggregateId") }

func (e *event) version() (int64, error) {
	value, err := e.body.field("version")
	if err != nil {
		return 0, err
	}
	if value.kind() == "number" {
		if n, err := strconv.ParseInt(strings.TrimSpace(string(value)), 10, 64); err == nil && n >= 0 {
			return n, nil
		}
	}
	return 0, bad("'version' is not a whole number")
}

func (e *event) data() (element, error) {
	value, err := e.body.field("data")
	if err != nil {
		return nil, err
	}
	if value.kind() != "object" {
		return nil, bad("'data' is not an object")
	}
	return value, nil
}

type slot struct {
	QuestionnaireTypeID uuid.UUID
	Order               int32
}

// typeData is a type's full state, from an event's or a snapshot's `data`.
type typeData struct {
	OwnerID              uuid.UUID
	Title                string
	CreatedAt, UpdatedAt time.Time
	QuestionnaireJSON    string
	Description          string
	Items                []slot
}

func parseTypeData(kind string, data element) (*typeData, error) {
	owner, err := data.uuid("ownerId")
	if err != nil {
		return nil, err
	}
	title, err := data.text("title")
	if err != nil {
		return nil, err
	}
	created, err := timestamp(data, "createdAt")
	if err != nil {
		return nil, err
	}
	updated, err := timestamp(data, "updatedAt")
	if err != nil {
		return nil, err
	}
	t := &typeData{OwnerID: owner, Title: title, CreatedAt: created, UpdatedAt: updated, QuestionnaireJSON: "{}"}
	if kind == QuestionnaireType {
		raw, err := data.field("questionnaireJson")
		if err != nil {
			return nil, err
		}
		t.QuestionnaireJSON = string(bytes.TrimSpace(raw))
		return t, nil
	}
	items, err := data.field("items")
	if err != nil {
		return nil, err
	}
	if items.kind() != "array" {
		return nil, bad("'items' is not a list")
	}
	var list []json.RawMessage
	_ = json.Unmarshal(items, &list)
	for _, raw := range list {
		item := element(raw)
		id, err := item.uuid("questionnaireTypeId")
		if err != nil {
			return nil, err
		}
		order, err := item.field("order")
		if err != nil {
			return nil, err
		}
		n, convErr := strconv.ParseInt(strings.TrimSpace(string(order)), 10, 32)
		if order.kind() != "number" || convErr != nil || n < 0 {
			return nil, bad("'order' is not a whole number")
		}
		t.Items = append(t.Items, slot{id, int32(n)})
	}
	if t.Description, err = data.text("description"); err != nil {
		return nil, err
	}
	return t, nil
}

var timeLayouts = []string{
	time.RFC3339Nano,
	"2006-01-02T15:04:05.999999999",
	"2006-01-02 15:04:05.999999999Z07:00",
	"2006-01-02 15:04:05.999999999",
	"2006-01-02",
}

// timestamp reads an ISO 8601 time; one with no offset is UTC, as .NET's AssumeUniversal.
func timestamp(data element, name string) (time.Time, error) {
	text, err := data.text(name)
	if err != nil {
		return time.Time{}, err
	}
	for _, layout := range timeLayouts {
		if parsed, err := time.Parse(layout, strings.TrimSpace(text)); err == nil {
			return parsed.UTC().Truncate(time.Microsecond), nil
		}
	}
	return time.Time{}, bad("'%s' is not a timestamp", name)
}
