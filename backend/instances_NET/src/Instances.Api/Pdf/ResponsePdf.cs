using System.Text.Json;
using Instances.Api.Data;
using QuestPDF.Fluent;
using QuestPDF.Helpers;
using QuestPDF.Infrastructure;

namespace Instances.Api.Pdf;

/// <summary>
/// A submitted response as a PDF (#43), drawn with QuestPDF: no browser, Pango or system
/// fonts on the host. The layout follows Django's `response_pdf.html` (title, respondent and
/// time, scores, then each question with its answer); the bytes differ, and the parity
/// suite compares the text.
/// </summary>
public static class ResponsePdf
{
    static readonly string Blue = "#1d4ed8";
    static readonly string Grey = "#737373";
    static readonly string Faint = "#a3a3a3";
    static readonly string Rule = "#e5e5e5";
    static readonly string Ink = "#171717";

    // Django's `N` date format: AP style month abbreviations.
    static readonly string[] Months =
        ["Jan.", "Feb.", "March", "April", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."];

    static ResponsePdf()
    {
        // The Community licence covers this project (README, #43).
        QuestPDF.Settings.License = LicenseType.Community;
    }

    public static byte[] Render(Questionnaire questionnaire)
    {
        using var snapshot = JsonDocument.Parse(questionnaire.QuestionnaireJsonSnapshot);
        using var answers = JsonDocument.Parse(questionnaire.AnswersJson);
        using var metrics = JsonDocument.Parse(questionnaire.MetricsJson);
        var questions = ResponseContent.Questions(snapshot.RootElement, answers.RootElement);
        var scores = ResponseContent.Metrics(snapshot.RootElement, metrics.RootElement);
        var title = questionnaire.QuestionnaireType.Title;
        var submitted = questionnaire.SubmittedAt!.Value;
        var meta = (questionnaire.Name.Length > 0 ? $"{questionnaire.Name} · " : "")
            + $"Submitted {submitted.Day} {Months[submitted.Month - 1]} {submitted.Year}, {submitted:HH:mm} UTC";

        return Document.Create(document => document.Page(page =>
        {
            page.Size(PageSizes.A4);
            page.MarginVertical(18, Unit.Millimetre);
            page.MarginHorizontal(15, Unit.Millimetre);
            // No kerning: text extraction would read a kerned pair ("To") as two words.
            page.DefaultTextStyle(style => style.FontSize(10).FontColor(Ink).LineHeight(1.5f)
                .DisableFontFeature(FontFeatures.Kerning));

            page.Header().BorderBottom(2).BorderColor(Blue).PaddingBottom(4, Unit.Millimetre).Column(header =>
            {
                header.Item().Text(title).FontSize(18).Bold();
                header.Item().Text(meta).FontSize(9).FontColor(Grey);
            });

            page.Content().PaddingTop(6, Unit.Millimetre).Column(content =>
            {
                if (scores.Count > 0)
                {
                    content.Item().Element(Section).Text("SCORES");
                    content.Item().Inlined(row =>
                    {
                        row.Spacing(4, Unit.Millimetre);
                        foreach (var score in scores)
                        {
                            row.Item().MinWidth(40, Unit.Millimetre).Border(1).BorderColor(Rule).CornerRadius(3)
                                .PaddingVertical(3, Unit.Millimetre).PaddingHorizontal(5, Unit.Millimetre)
                                .Column(box =>
                                {
                                    box.Item().Text(score.Label).FontSize(8.5f).FontColor(Grey);
                                    box.Item().Text(score.Value).FontSize(16).Bold().FontColor(Blue);
                                });
                        }
                    });
                }

                content.Item().Element(Section).Text("RESPONSES");
                if (questions.Count == 0)
                {
                    content.Item().Text("This questionnaire has no questions.").Italic().FontColor(Faint);
                }
                foreach (var question in questions)
                {
                    content.Item().PaddingBottom(3, Unit.Millimetre).ShowEntire().Border(1).BorderColor(Rule)
                        .CornerRadius(3).PaddingVertical(4, Unit.Millimetre).PaddingHorizontal(5, Unit.Millimetre)
                        .Column(box =>
                        {
                            box.Item().PaddingBottom(1, Unit.Millimetre).Text(question.Title).SemiBold();
                            switch (question)
                            {
                                case MatrixQuestion matrix:
                                    box.Item().Element(container => Matrix(container, matrix));
                                    break;
                                case AnswerQuestion { DisplayValue.Length: > 0 } answer:
                                    box.Item().Text(answer.DisplayValue).FontColor("#404040");
                                    break;
                                default:
                                    box.Item().Text("No answer").Italic().FontColor(Faint);
                                    break;
                            }
                        });
                }
            });

            page.Footer().AlignCenter().Text(text =>
            {
                text.DefaultTextStyle(style => style.FontSize(8).FontColor(Grey));
                text.Span("Page ");
                text.CurrentPageNumber();
                text.Span(" of ");
                text.TotalPages();
            });
        })).GeneratePdf();
    }

    static IContainer Section(IContainer container) =>
        container.PaddingTop(6, Unit.Millimetre).PaddingBottom(3, Unit.Millimetre)
            .DefaultTextStyle(style => style.FontSize(8).SemiBold().FontColor(Grey).LetterSpacing(0.05f));

    static void Matrix(IContainer container, MatrixQuestion matrix) =>
        container.PaddingTop(2, Unit.Millimetre).DefaultTextStyle(style => style.FontSize(9)).Table(table =>
        {
            table.ColumnsDefinition(columns =>
            {
                columns.RelativeColumn(2);
                foreach (var _ in matrix.Columns)
                {
                    columns.RelativeColumn();
                }
            });
            table.Header(header =>
            {
                header.Cell().Element(HeaderCell).Text("");
                foreach (var column in matrix.Columns)
                {
                    header.Cell().Element(HeaderCell).AlignCenter().Text(column).FontColor(Grey).SemiBold();
                }
            });
            foreach (var row in matrix.Rows)
            {
                table.Cell().Element(BodyCell).Text(row.Label);
                foreach (var column in matrix.Columns)
                {
                    var on = row.Selected == column;
                    table.Cell().Element(BodyCell).AlignCenter().AlignMiddle()
                        .Width(4, Unit.Millimetre).Height(4, Unit.Millimetre)
                        .Border(1.2f).BorderColor(Blue).CornerRadius(6)
                        .Background(on ? Blue : Colors.Transparent);
                }
            }
        });

    static IContainer HeaderCell(IContainer container) =>
        container.BorderBottom(1).BorderColor(Rule).PaddingVertical(1.5f, Unit.Millimetre).PaddingHorizontal(2, Unit.Millimetre);

    static IContainer BodyCell(IContainer container) =>
        container.BorderBottom(0.5f).BorderColor(Rule).PaddingVertical(1.5f, Unit.Millimetre).PaddingHorizontal(2, Unit.Millimetre);
}
