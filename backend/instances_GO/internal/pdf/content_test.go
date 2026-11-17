package pdf

import (
	"strings"
	"testing"

	"instances/internal/ojson"
)

func parse(t *testing.T, text string) *ojson.Value {
	t.Helper()
	v, err := ojson.Parse([]byte(text))
	if err != nil {
		t.Fatal(err)
	}
	return v
}

func TestQuestionsResolveLabelsInDisplayOrder(t *testing.T) {
	survey := parse(t, `{"pages": [{"elements": [
		{"type": "radiogroup", "name": "fruit", "title": "Fruit", "choices": [{"value": "a", "text": "Apple"}, "Pear"]},
		{"type": "html", "name": "x"},
		{"type": "panel", "elements": [{"type": "comment", "name": "inside"}]},
		{"type": "checkbox", "name": "many", "choices": [1, {"value": 2, "text": "Two"}]},
		{"type": "boolean", "name": "ok"},
		{"type": "text", "name": "blank"},
		{"type": "matrix", "name": "m", "columns": [{"value": 1, "text": "Rarely"}], "rows": [{"value": "r", "text": "Row"}]}
	]}]}`)
	answers := parse(t, `{"fruit": "a", "inside": "Hi", "many": [1, 2], "ok": false, "blank": "", "m": {"r": 1}}`)
	got := Questions(survey, answers)
	want := []string{"Fruit=Apple", "inside=Hi", "many=1, Two", "ok=No", "blank="}
	for i, w := range want {
		if line := got[i].Title + "=" + got[i].Answer; line != w {
			t.Errorf("question %d: %q, want %q", i, line, w)
		}
	}
	matrix := got[5]
	if !matrix.Matrix || matrix.Columns[0] != "Rarely" || *matrix.Rows[0].Selected != "Rarely" {
		t.Fatalf("%+v", matrix)
	}
}

func TestMetricsAreLabelledByTitleOrTitleCase(t *testing.T) {
	survey := parse(t, `{"calculatedValues": [{"name": "total", "title": "Total score"}, {"name": "sub_score"},
		{"name": "absent", "title": "Never"}]}`)
	got := Metrics(survey, parse(t, `{"total": 17, "sub_score": 4.0}`))
	if len(got) != 2 || got[0] != (Metric{"Total score", "17"}) || got[1] != (Metric{"Sub Score", "4.0"}) {
		t.Fatalf("%+v", got)
	}
}

func TestPythonStrOfJSON(t *testing.T) {
	for raw, want := range map[string]string{
		`1`: "1", `2.0`: "2.0", `1.5`: "1.5", `1e16`: "1e+16", `100000.0`: "100000.0", `0.00001`: "1e-05",
		`1e100`: "1e+100", `true`: "True", `null`: "None", `["a", 1, false]`: "['a', 1, False]",
		`{"k": "v", "n": [1]}`: "{'k': 'v', 'n': [1]}",
	} {
		if got := parse(t, raw).PyStr(); got != want {
			t.Errorf("str(%s) = %q, want %q", raw, got, want)
		}
	}
}

func TestPythonTitle(t *testing.T) {
	if got := PythonTitle("sub score 2nd x"); got != "Sub Score 2Nd X" {
		t.Fatal(got)
	}
}

func TestRenderWritesAPDF(t *testing.T) {
	content, err := Render(Response{TypeTitle: "Mood · ünïcode", Name: "Alice",
		Snapshot: `{"pages": []}`, Answers: `{}`, MetricsRaw: `{}`})
	if err != nil || !strings.HasPrefix(string(content), "%PDF-") {
		t.Fatalf("%v %q", err, content[:min(len(content), 10)])
	}
}
