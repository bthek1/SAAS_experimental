// Package ojson reads JSON keeping object members in document order, as .NET's
// JsonElement and Python's dict do: the dashboard's scores and the PDF's labels depend on
// that order, which Go's maps lose.
package ojson

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strconv"
	"strings"
)

// Value is one JSON value.
type Value struct {
	Kind   string // object, array, string, number, bool, null
	Str    string
	Num    json.Number
	Bool   bool
	Items  []*Value
	Keys   []string
	fields map[string]*Value
}

// Parse reads one JSON document.
func Parse(data []byte) (*Value, error) {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	value, err := read(decoder)
	if err != nil {
		return nil, err
	}
	if _, err := decoder.Token(); !errors.Is(err, io.EOF) {
		return nil, errors.New("ojson: trailing data")
	}
	return value, nil
}

func read(d *json.Decoder) (*Value, error) {
	token, err := d.Token()
	if err != nil {
		return nil, err
	}
	switch t := token.(type) {
	case json.Delim:
		if t == '{' {
			v := &Value{Kind: "object", fields: map[string]*Value{}}
			for d.More() {
				keyToken, err := d.Token()
				if err != nil {
					return nil, err
				}
				key := keyToken.(string)
				member, err := read(d)
				if err != nil {
					return nil, err
				}
				if _, seen := v.fields[key]; !seen {
					v.Keys = append(v.Keys, key)
				}
				// A repeated key: the last one, as Python's json and jsonb keep.
				v.fields[key] = member
			}
			_, err := d.Token()
			return v, err
		}
		v := &Value{Kind: "array"}
		for d.More() {
			item, err := read(d)
			if err != nil {
				return nil, err
			}
			v.Items = append(v.Items, item)
		}
		_, err := d.Token()
		return v, err
	case string:
		return &Value{Kind: "string", Str: t}, nil
	case json.Number:
		return &Value{Kind: "number", Num: t}, nil
	case bool:
		return &Value{Kind: "bool", Bool: t}, nil
	}
	return &Value{Kind: "null"}, nil
}

// Get is an object's member, or nil.
func (v *Value) Get(key string) *Value {
	if v == nil || v.Kind != "object" {
		return nil
	}
	return v.fields[key]
}

// StringField is a member that is a string, or ("", false).
func (v *Value) StringField(key string) (string, bool) {
	member := v.Get(key)
	if member == nil || member.Kind != "string" {
		return "", false
	}
	return member.Str, true
}

// Float is a number's value.
func (v *Value) Float() float64 {
	f, _ := strconv.ParseFloat(string(v.Num), 64)
	return f
}

// Truthy is Python's truth of the value.
func (v *Value) Truthy() bool {
	switch v.Kind {
	case "string":
		return v.Str != ""
	case "number":
		return v.Float() != 0
	case "bool":
		return v.Bool
	case "object":
		return len(v.Keys) > 0
	case "array":
		return len(v.Items) > 0
	}
	return false
}

// Raw is the value as compact JSON, members in their order.
func (v *Value) Raw() json.RawMessage {
	var b bytes.Buffer
	v.write(&b)
	return b.Bytes()
}

func (v *Value) write(b *bytes.Buffer) {
	switch v.Kind {
	case "object":
		b.WriteByte('{')
		for i, key := range v.Keys {
			if i > 0 {
				b.WriteByte(',')
			}
			writeString(b, key)
			b.WriteByte(':')
			v.fields[key].write(b)
		}
		b.WriteByte('}')
	case "array":
		b.WriteByte('[')
		for i, item := range v.Items {
			if i > 0 {
				b.WriteByte(',')
			}
			item.write(b)
		}
		b.WriteByte(']')
	case "string":
		writeString(b, v.Str)
	case "number":
		b.WriteString(string(v.Num))
	case "bool":
		b.WriteString(strconv.FormatBool(v.Bool))
	default:
		b.WriteString("null")
	}
}

func writeString(b *bytes.Buffer, s string) {
	encoder := json.NewEncoder(b)
	encoder.SetEscapeHTML(false)
	_ = encoder.Encode(s)
	b.Truncate(b.Len() - 1)
}

// PyStr is Python's `str()` of the value, as Django's template printed it.
func (v *Value) PyStr() string {
	switch v.Kind {
	case "string":
		return v.Str
	case "bool":
		if v.Bool {
			return "True"
		}
		return "False"
	case "null":
		return "None"
	case "number":
		return PyNumber(string(v.Num))
	case "array":
		parts := make([]string, len(v.Items))
		for i, item := range v.Items {
			parts[i] = item.pyRepr()
		}
		return "[" + strings.Join(parts, ", ") + "]"
	}
	parts := make([]string, len(v.Keys))
	for i, key := range v.Keys {
		parts[i] = "'" + key + "': " + v.fields[key].pyRepr()
	}
	return "{" + strings.Join(parts, ", ") + "}"
}

func (v *Value) pyRepr() string {
	if v.Kind == "string" {
		return "'" + v.Str + "'"
	}
	return v.PyStr()
}

// PyNumber prints a JSON number as Python does: an int stays an int; a float is its
// shortest repr (`2.0`, `1.5`, `1e+16`).
func PyNumber(raw string) string {
	if !strings.ContainsAny(raw, ".eE") {
		return raw
	}
	f, err := strconv.ParseFloat(raw, 64)
	if err != nil {
		return raw
	}
	scientific := strconv.FormatFloat(f, 'e', -1, 64)
	mantissa, exponentText, _ := strings.Cut(scientific, "e")
	exponent, _ := strconv.Atoi(exponentText)
	if exponent >= -4 && exponent < 16 {
		text := strconv.FormatFloat(f, 'f', -1, 64)
		if !strings.Contains(text, ".") {
			text += ".0"
		}
		return text
	}
	sign := "+"
	if exponent < 0 {
		sign, exponent = "-", -exponent
	}
	return mantissa + "e" + sign + fmt.Sprintf("%02d", exponent)
}
