using System.Globalization;
using System.Text;
using System.Text.Json;

namespace Instances.Api.Pdf;

public abstract record ResolvedQuestion(string Title);

public sealed record AnswerQuestion(string Title, string Type, string DisplayValue) : ResolvedQuestion(Title);

public sealed record MatrixRow(string Label, string? Selected);

public sealed record MatrixQuestion(string Title, IReadOnlyList<string> Columns, IReadOnlyList<MatrixRow> Rows) : ResolvedQuestion(Title);

public sealed record ResolvedMetric(string Label, string Value);

/// <summary>
/// What a submitted response says, ready to draw: Django's `pdf.py`, ported. Questions in
/// display order (panels flattened, html, images and expressions left out), answers by
/// their display labels, scores labelled by the survey's `calculatedValues`. Always read
/// against the definition the response was answered with (its snapshot).
/// </summary>
public static class ResponseContent
{
    static readonly HashSet<string> NotQuestions = ["html", "image", "expression"];

    public static IReadOnlyList<ResolvedQuestion> Questions(JsonElement survey, JsonElement answers)
    {
        var questions = new List<ResolvedQuestion>();
        if (survey.ValueKind != JsonValueKind.Object || !survey.TryGetProperty("pages", out var pages)
            || pages.ValueKind != JsonValueKind.Array)
        {
            return questions;
        }
        foreach (var page in pages.EnumerateArray())
        {
            if (page.ValueKind != JsonValueKind.Object)
            {
                continue;
            }
            foreach (var element in Elements(page))
            {
                var type = Str(element, "type") ?? "";
                if (NotQuestions.Contains(type))
                {
                    continue;
                }
                var name = Str(element, "name") ?? "";
                var title = element.TryGetProperty("title", out var t) && Truthy(t) ? PyStr(t) : name;
                var raw = answers.ValueKind == JsonValueKind.Object && answers.TryGetProperty(name, out var a) ? a : (JsonElement?)null;
                if (type == "matrix")
                {
                    var columns = LabelMap(element, "columns");
                    var rowAnswers = raw is { ValueKind: JsonValueKind.Object } given ? given : (JsonElement?)null;
                    var rows = LabelMap(element, "rows").Select(row =>
                    {
                        string? selected = null;
                        if (rowAnswers is { } chosen && chosen.TryGetProperty(row.Key, out var picked))
                        {
                            selected = columns.GetValueOrDefault(PyStr(picked));
                        }
                        return new MatrixRow(row.Value, selected);
                    }).ToList();
                    questions.Add(new MatrixQuestion(title, columns.Values.ToList(), rows));
                }
                else
                {
                    questions.Add(new AnswerQuestion(title, type, Display(element, raw)));
                }
            }
        }
        return questions;
    }

    public static IReadOnlyList<ResolvedMetric> Metrics(JsonElement survey, JsonElement metrics)
    {
        var resolved = new List<ResolvedMetric>();
        if (survey.ValueKind != JsonValueKind.Object || metrics.ValueKind != JsonValueKind.Object
            || !survey.TryGetProperty("calculatedValues", out var definitions) || definitions.ValueKind != JsonValueKind.Array)
        {
            return resolved;
        }
        foreach (var definition in definitions.EnumerateArray())
        {
            if (definition.ValueKind != JsonValueKind.Object || Str(definition, "name") is not { } name
                || !metrics.TryGetProperty(name, out var value))
            {
                continue;
            }
            var label = definition.TryGetProperty("title", out var title) && Truthy(title)
                ? PyStr(title)
                : PythonTitle(name.Replace('_', ' '));
            resolved.Add(new ResolvedMetric(label, PyStr(value)));
        }
        return resolved;
    }

    /// <summary>Questions in display order, panels flattened.</summary>
    static IEnumerable<JsonElement> Elements(JsonElement container)
    {
        if (!container.TryGetProperty("elements", out var elements) || elements.ValueKind != JsonValueKind.Array)
        {
            yield break;
        }
        foreach (var element in elements.EnumerateArray())
        {
            if (element.ValueKind != JsonValueKind.Object)
            {
                continue;
            }
            if (Str(element, "type") == "panel")
            {
                foreach (var inner in Elements(element))
                {
                    yield return inner;
                }
            }
            else
            {
                yield return element;
            }
        }
    }

    /// <summary>SurveyJS choice, row or column values to their display text, in order.</summary>
    static Dictionary<string, string> LabelMap(JsonElement element, string property)
    {
        var labels = new Dictionary<string, string>();
        if (!element.TryGetProperty(property, out var items) || items.ValueKind != JsonValueKind.Array)
        {
            return labels;
        }
        foreach (var item in items.EnumerateArray())
        {
            if (item.ValueKind == JsonValueKind.Object)
            {
                var value = item.TryGetProperty("value", out var v) ? PyStr(v) : "";
                labels[value] = item.TryGetProperty("text", out var text) ? PyStr(text) : value;
            }
            else
            {
                labels[PyStr(item)] = PyStr(item);
            }
        }
        return labels;
    }

    static string Display(JsonElement element, JsonElement? answer)
    {
        if (answer is not { } raw || raw.ValueKind == JsonValueKind.Null
            || (raw.ValueKind == JsonValueKind.String && raw.GetString() == ""))
        {
            return "";
        }
        if (raw.ValueKind is JsonValueKind.True or JsonValueKind.False)
        {
            return raw.ValueKind == JsonValueKind.True ? "Yes" : "No";
        }
        var labels = LabelMap(element, "choices");
        var values = raw.ValueKind == JsonValueKind.Array ? raw.EnumerateArray().ToList() : [raw];
        if (values.All(v => v.ValueKind is JsonValueKind.String or JsonValueKind.Number or JsonValueKind.True or JsonValueKind.False))
        {
            return string.Join(", ", values.Select(v => labels.GetValueOrDefault(PyStr(v), PyStr(v))));
        }
        return PyStr(raw);
    }

    static string? Str(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;

    static bool Truthy(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.String => value.GetString() != "",
        JsonValueKind.Number => value.GetDouble() != 0,
        JsonValueKind.True => true,
        JsonValueKind.Object => value.EnumerateObject().Any(),
        JsonValueKind.Array => value.GetArrayLength() > 0,
        _ => false,
    };

    /// <summary>Python's `str()` of a JSON value, as Django's template printed it.</summary>
    public static string PyStr(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.String => value.GetString()!,
        JsonValueKind.True => "True",
        JsonValueKind.False => "False",
        JsonValueKind.Null => "None",
        JsonValueKind.Number => PyNumber(value),
        JsonValueKind.Array => "[" + string.Join(", ", value.EnumerateArray().Select(PyRepr)) + "]",
        _ => "{" + string.Join(", ", value.EnumerateObject().Select(p => $"'{p.Name}': {PyRepr(p.Value)}")) + "}",
    };

    static string PyRepr(JsonElement value) =>
        value.ValueKind == JsonValueKind.String ? $"'{value.GetString()}'" : PyStr(value);

    /// <summary>An int stays an int; a float prints as Python's shortest repr (`2.0`, `1.5`).</summary>
    static string PyNumber(JsonElement value)
    {
        var raw = value.GetRawText();
        if (raw.IndexOfAny(['.', 'e', 'E']) < 0)
        {
            return raw;
        }
        var number = value.GetDouble();
        var text = number.ToString("R", CultureInfo.InvariantCulture);
        if (text.Contains('E'))
        {
            var parts = text.Split('E');
            var exponent = int.Parse(parts[1], CultureInfo.InvariantCulture);
            if (exponent is >= -4 and < 16)
            {
                text = number.ToString("0.################", CultureInfo.InvariantCulture);
            }
            else
            {
                return $"{parts[0]}e{(exponent < 0 ? "-" : "+")}{Math.Abs(exponent):D2}";
            }
        }
        return text.Contains('.') ? text : text + ".0";
    }

    /// <summary>Python's `str.title()`: a letter after a non-letter starts a word.</summary>
    public static string PythonTitle(string text)
    {
        var builder = new StringBuilder(text.Length);
        var previousIsLetter = false;
        foreach (var c in text)
        {
            builder.Append(previousIsLetter ? char.ToLowerInvariant(c) : char.ToUpperInvariant(c));
            previousIsLetter = char.IsLetter(c);
        }
        return builder.ToString();
    }
}
