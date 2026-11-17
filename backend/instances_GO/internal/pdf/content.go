// Package pdf draws a submitted response as a PDF (#43, #52). content.go resolves what a
// response says, as instances_NET's Pdf/ResponseContent.cs (Django's pdf.py, ported);
// render.go draws it. The parity suite compares the text, never the bytes.
package pdf

import (
	"strings"
	"unicode"

	"instances/internal/ojson"
)

// Question is one question in display order. A matrix has Columns and Rows; any other
// question has Answer ("" when not answered).
type Question struct {
	Title   string
	Answer  string
	Matrix  bool
	Columns []string
	Rows    []MatrixRow
}

// MatrixRow is one row of a matrix question, and the column chosen (nil if none).
type MatrixRow struct {
	Label    string
	Selected *string
}

// Metric is one score, labelled.
type Metric struct{ Label, Value string }

var notQuestions = map[string]bool{"html": true, "image": true, "expression": true}

// Questions are the survey's questions in display order (panels flattened, html, images
// and expressions left out), answers by their display labels. Always read against the
// definition the response was answered with (its snapshot).
func Questions(survey, answers *ojson.Value) []Question {
	questions := []Question{}
	pages := survey.Get("pages")
	if pages == nil || pages.Kind != "array" {
		return questions
	}
	for _, page := range pages.Items {
		if page.Kind != "object" {
			continue
		}
		for _, element := range elements(page) {
			kind, _ := element.StringField("type")
			if notQuestions[kind] {
				continue
			}
			name, _ := element.StringField("name")
			title := name
			if t := element.Get("title"); t != nil && t.Truthy() {
				title = t.PyStr()
			}
			raw := answers.Get(name)
			if kind != "matrix" {
				questions = append(questions, Question{Title: title, Answer: display(element, raw)})
				continue
			}
			columns := labelMap(element, "columns")
			q := Question{Title: title, Matrix: true}
			for _, key := range columns.keys {
				q.Columns = append(q.Columns, columns.labels[key])
			}
			rows := labelMap(element, "rows")
			for _, key := range rows.keys {
				row := MatrixRow{Label: rows.labels[key]}
				if raw != nil && raw.Kind == "object" {
					if picked := raw.Get(key); picked != nil {
						if label, ok := columns.labels[picked.PyStr()]; ok {
							row.Selected = &label
						}
					}
				}
				q.Rows = append(q.Rows, row)
			}
			questions = append(questions, q)
		}
	}
	return questions
}

// Metrics are the stored scores the survey's `calculatedValues` name, labelled by their
// titles or by the name in title case.
func Metrics(survey, metrics *ojson.Value) []Metric {
	resolved := []Metric{}
	definitions := survey.Get("calculatedValues")
	if metrics == nil || metrics.Kind != "object" || definitions == nil || definitions.Kind != "array" {
		return resolved
	}
	for _, definition := range definitions.Items {
		name, ok := definition.StringField("name")
		if !ok || definition.Kind != "object" {
			continue
		}
		value := metrics.Get(name)
		if value == nil {
			continue
		}
		label := PythonTitle(strings.ReplaceAll(name, "_", " "))
		if t := definition.Get("title"); t != nil && t.Truthy() {
			label = t.PyStr()
		}
		resolved = append(resolved, Metric{label, value.PyStr()})
	}
	return resolved
}

func elements(container *ojson.Value) []*ojson.Value {
	list := container.Get("elements")
	if list == nil || list.Kind != "array" {
		return nil
	}
	var out []*ojson.Value
	for _, element := range list.Items {
		if element.Kind != "object" {
			continue
		}
		if kind, _ := element.StringField("type"); kind == "panel" {
			out = append(out, elements(element)...)
		} else {
			out = append(out, element)
		}
	}
	return out
}

type labels struct {
	keys   []string
	labels map[string]string
}

// labelMap maps SurveyJS choice, row or column values to their display text, in order.
func labelMap(element *ojson.Value, property string) labels {
	m := labels{labels: map[string]string{}}
	items := element.Get(property)
	if items == nil || items.Kind != "array" {
		return m
	}
	for _, item := range items.Items {
		var value, text string
		if item.Kind == "object" {
			if v := item.Get("value"); v != nil {
				value = v.PyStr()
			}
			text = value
			if t := item.Get("text"); t != nil {
				text = t.PyStr()
			}
		} else {
			value, text = item.PyStr(), item.PyStr()
		}
		if _, seen := m.labels[value]; !seen {
			m.keys = append(m.keys, value)
		}
		m.labels[value] = text
	}
	return m
}

func display(element, answer *ojson.Value) string {
	if answer == nil || answer.Kind == "null" || (answer.Kind == "string" && answer.Str == "") {
		return ""
	}
	if answer.Kind == "bool" {
		if answer.Bool {
			return "Yes"
		}
		return "No"
	}
	choices := labelMap(element, "choices")
	values := []*ojson.Value{answer}
	if answer.Kind == "array" {
		values = answer.Items
	}
	parts := make([]string, 0, len(values))
	for _, v := range values {
		if v.Kind != "string" && v.Kind != "number" && v.Kind != "bool" {
			return answer.PyStr()
		}
		text := v.PyStr()
		if label, ok := choices.labels[text]; ok {
			text = label
		}
		parts = append(parts, text)
	}
	return strings.Join(parts, ", ")
}

// PythonTitle is Python's `str.title()`: a letter after a non-letter starts a word.
func PythonTitle(text string) string {
	var b strings.Builder
	previousIsLetter := false
	for _, c := range text {
		if previousIsLetter {
			b.WriteRune(unicode.ToLower(c))
		} else {
			b.WriteRune(unicode.ToUpper(c))
		}
		previousIsLetter = unicode.IsLetter(c)
	}
	return b.String()
}
