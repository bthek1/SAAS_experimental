package pdf

import (
	"bytes"
	"fmt"
	"time"

	"github.com/go-pdf/fpdf"

	"instances/internal/ojson"
)

// Response is what the PDF reads from a submitted questionnaire.
type Response struct {
	TypeTitle, Name               string
	SubmittedAt                   time.Time
	Snapshot, Answers, MetricsRaw string
}

// Django's `N` date format: AP style month abbreviations.
var months = []string{"Jan.", "Feb.", "March", "April", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."}

type rgb struct{ r, g, b int }

var (
	blue  = rgb{0x1d, 0x4e, 0xd8}
	grey  = rgb{0x73, 0x73, 0x73}
	faint = rgb{0xa3, 0xa3, 0xa3}
	rule  = rgb{0xe5, 0xe5, 0xe5}
	ink   = rgb{0x17, 0x17, 0x17}
	soft  = rgb{0x40, 0x40, 0x40}
)

const (
	marginX = 15.0
	marginY = 18.0
	width   = 210.0 - 2*marginX
)

// Render draws the response, following Django's response_pdf.html: title, respondent and
// time, scores, then each question with its answer. Core fonts only (Helvetica), so the
// host needs no font files; text is written in cp1252, which pypdf extracts as written.
func Render(response Response) ([]byte, error) {
	survey, err := ojson.Parse([]byte(response.Snapshot))
	if err != nil {
		return nil, err
	}
	answers, err := ojson.Parse([]byte(response.Answers))
	if err != nil {
		return nil, err
	}
	metrics, err := ojson.Parse([]byte(response.MetricsRaw))
	if err != nil {
		return nil, err
	}
	questions := Questions(survey, answers)
	scores := Metrics(survey, metrics)

	doc := fpdf.New("P", "mm", "A4", "")
	doc.SetMargins(marginX, marginY, marginX)
	doc.SetAutoPageBreak(true, marginY+6)
	doc.SetCreator("instances", true)
	doc.AliasNbPages("{nb}")
	tr := doc.UnicodeTranslatorFromDescriptor("")
	color := func(c rgb) { doc.SetTextColor(c.r, c.g, c.b) }
	doc.SetFooterFunc(func() {
		doc.SetY(-12)
		doc.SetFont("Helvetica", "", 8)
		color(grey)
		doc.CellFormat(0, 4, fmt.Sprintf("Page %d of {nb}", doc.PageNo()), "", 0, "C", false, 0, "")
	})
	doc.AddPage()

	submitted := response.SubmittedAt.UTC()
	meta := fmt.Sprintf("Submitted %d %s %d, %s UTC", submitted.Day(), months[submitted.Month()-1], submitted.Year(),
		submitted.Format("15:04"))
	if response.Name != "" {
		meta = response.Name + " · " + meta
	}
	doc.SetFont("Helvetica", "B", 18)
	color(ink)
	doc.MultiCell(width, 8, tr(response.TypeTitle), "", "L", false)
	doc.SetFont("Helvetica", "", 9)
	color(grey)
	doc.MultiCell(width, 5, tr(meta), "", "L", false)
	doc.Ln(3)
	y := doc.GetY()
	doc.SetDrawColor(blue.r, blue.g, blue.b)
	doc.SetLineWidth(0.7)
	doc.Line(marginX, y, marginX+width, y)
	doc.Ln(6)

	section := func(title string) {
		doc.Ln(2)
		doc.SetFont("Helvetica", "B", 8)
		color(grey)
		doc.CellFormat(width, 5, title, "", 1, "L", false, 0, "")
		doc.Ln(2)
	}
	doc.SetLineWidth(0.25)
	doc.SetDrawColor(rule.r, rule.g, rule.b)

	if len(scores) > 0 {
		section("SCORES")
		const boxWidth, boxHeight, gap = 42.0, 16.0, 4.0
		x := marginX
		for _, score := range scores {
			if x+boxWidth > marginX+width {
				x = marginX
				doc.SetY(doc.GetY() + boxHeight + gap)
			}
			top := doc.GetY()
			doc.RoundedRect(x, top, boxWidth, boxHeight, 1.5, "1234", "D")
			doc.SetXY(x+4, top+2)
			doc.SetFont("Helvetica", "", 8.5)
			color(grey)
			doc.CellFormat(boxWidth-8, 4.5, tr(score.Label), "", 2, "L", false, 0, "")
			doc.SetX(x + 4)
			doc.SetFont("Helvetica", "B", 16)
			color(blue)
			doc.CellFormat(boxWidth-8, 8, tr(score.Value), "", 0, "L", false, 0, "")
			doc.SetY(top)
			x += boxWidth + gap
		}
		doc.SetY(doc.GetY() + boxHeight + 2)
	}

	section("RESPONSES")
	if len(questions) == 0 {
		doc.SetFont("Helvetica", "I", 10)
		color(faint)
		doc.MultiCell(width, 6, "This questionnaire has no questions.", "", "L", false)
	}
	for _, question := range questions {
		drawQuestion(doc, tr, color, question)
	}

	var out bytes.Buffer
	if err := doc.Output(&out); err != nil {
		return nil, err
	}
	return out.Bytes(), nil
}

// drawQuestion draws one question in a box, kept on one page when it fits.
func drawQuestion(doc *fpdf.Fpdf, tr func(string) string, color func(rgb), q Question) {
	const pad = 4.0
	inner := width - 2*pad
	doc.SetFont("Helvetica", "B", 10)
	titleLines := len(doc.SplitText(tr(q.Title), inner))
	height := pad*2 + float64(titleLines)*6 + 1
	if q.Matrix {
		height += 7 * float64(len(q.Rows)+1)
	} else {
		doc.SetFont("Helvetica", "", 10)
		answer := q.Answer
		if answer == "" {
			answer = "No answer"
		}
		height += float64(len(doc.SplitText(tr(answer), inner))) * 6
	}
	_, pageHeight := doc.GetPageSize()
	if doc.GetY()+height > pageHeight-marginY-6 && height < pageHeight-2*marginY {
		doc.AddPage()
	}
	top := doc.GetY()
	doc.SetXY(marginX+pad, top+pad)
	doc.SetFont("Helvetica", "B", 10)
	color(ink)
	doc.MultiCell(inner, 6, tr(q.Title), "", "L", false)
	doc.Ln(1)
	switch {
	case q.Matrix:
		drawMatrix(doc, tr, color, q, inner)
	case q.Answer != "":
		doc.SetX(marginX + pad)
		doc.SetFont("Helvetica", "", 10)
		color(soft)
		doc.MultiCell(inner, 6, tr(q.Answer), "", "L", false)
	default:
		doc.SetX(marginX + pad)
		doc.SetFont("Helvetica", "I", 10)
		color(faint)
		doc.MultiCell(inner, 6, "No answer", "", "L", false)
	}
	bottom := doc.GetY() + pad
	doc.SetDrawColor(rule.r, rule.g, rule.b)
	if bottom > top {
		doc.RoundedRect(marginX, top, width, bottom-top, 1.5, "1234", "D")
	}
	doc.SetY(bottom + 3)
}

func drawMatrix(doc *fpdf.Fpdf, tr func(string) string, color func(rgb), q Question, inner float64) {
	columns := float64(len(q.Columns))
	labelWidth := inner * 2 / (2 + columns)
	cellWidth := (inner - labelWidth) / max(columns, 1)
	left := marginX + 4
	doc.SetFont("Helvetica", "B", 9)
	color(grey)
	doc.SetX(left)
	doc.CellFormat(labelWidth, 7, "", "B", 0, "L", false, 0, "")
	for _, column := range q.Columns {
		doc.CellFormat(cellWidth, 7, tr(column), "B", 0, "C", false, 0, "")
	}
	doc.Ln(-1)
	doc.SetFont("Helvetica", "", 9)
	for _, row := range q.Rows {
		color(ink)
		doc.SetX(left)
		y := doc.GetY()
		doc.CellFormat(labelWidth, 7, tr(row.Label), "B", 0, "L", false, 0, "")
		for i, column := range q.Columns {
			cx := left + labelWidth + cellWidth*float64(i) + cellWidth/2
			doc.SetDrawColor(blue.r, blue.g, blue.b)
			doc.SetFillColor(blue.r, blue.g, blue.b)
			style := "D"
			if row.Selected != nil && *row.Selected == column {
				style = "FD"
			}
			doc.Circle(cx, y+3.5, 1.8, style)
		}
		doc.SetDrawColor(rule.r, rule.g, rule.b)
		doc.Line(left+labelWidth, y+7, left+inner, y+7)
		doc.SetY(y + 7)
	}
}
