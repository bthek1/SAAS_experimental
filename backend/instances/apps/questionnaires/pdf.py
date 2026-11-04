"""PDF export of a submitted questionnaire response."""

from typing import Any

from django.template.loader import render_to_string

from .models import Questionnaire


def _label_map(items: list[Any]) -> dict[str, str]:
    """Map SurveyJS choice/row/column values to their display text."""
    labels: dict[str, str] = {}
    for item in items:
        if isinstance(item, dict):
            value = item.get("value", "")
            labels[str(value)] = str(item.get("text", value))
        else:
            labels[str(item)] = str(item)
    return labels


def _display(element: dict[str, Any], raw: Any) -> str:
    if raw is None or raw == "":
        return ""
    if isinstance(raw, bool):
        return "Yes" if raw else "No"
    labels = _label_map(element.get("choices", []))
    values = raw if isinstance(raw, list) else [raw]
    if all(isinstance(v, (str, int, float)) for v in values):
        return ", ".join(labels.get(str(v), str(v)) for v in values)
    return str(raw)


def _elements(container: dict[str, Any]) -> list[dict[str, Any]]:
    """Questions in display order, flattening panels."""
    out: list[dict[str, Any]] = []
    for element in container.get("elements", []):
        if not isinstance(element, dict):
            continue
        if element.get("type") == "panel":
            out.extend(_elements(element))
        else:
            out.append(element)
    return out


def resolve_questions(
    survey_json: dict[str, Any], answers: dict[str, Any]
) -> list[dict[str, Any]]:
    """Flat list of {title, type, display_value} (or matrix rows) for the template."""
    questions: list[dict[str, Any]] = []
    for page in survey_json.get("pages", []):
        if not isinstance(page, dict):
            continue
        for element in _elements(page):
            if element.get("type") in {"html", "image", "expression"}:
                continue
            name = element.get("name", "")
            title = element.get("title") or name
            raw = answers.get(name)
            if element.get("type") == "matrix":
                columns = _label_map(element.get("columns", []))
                row_answers = raw if isinstance(raw, dict) else {}
                row_labels = _label_map(element.get("rows", []))
                rows = [
                    {
                        "label": row_label,
                        "selected": columns.get(str(row_answers.get(row_value)))
                        if row_value in row_answers
                        else None,
                    }
                    for row_value, row_label in row_labels.items()
                ]
                questions.append(
                    {
                        "title": title,
                        "type": "matrix",
                        "columns": list(columns.values()),
                        "rows": rows,
                    }
                )
            else:
                questions.append(
                    {
                        "title": title,
                        "type": element.get("type", ""),
                        "display_value": _display(element, raw),
                    }
                )
    return questions


def resolve_metrics(
    survey_json: dict[str, Any], metrics: dict[str, Any]
) -> list[dict[str, Any]]:
    """Stored metrics labelled by the survey's calculatedValues, in definition order."""
    out = []
    for definition in survey_json.get("calculatedValues", []):
        if isinstance(definition, dict) and definition.get("name") in metrics:
            name = definition["name"]
            label = definition.get("title") or name.replace("_", " ").title()
            out.append({"label": label, "value": metrics[name]})
    return out


def render_response_html(instance: Questionnaire) -> str:
    # Read the response against the definition it was answered with.
    survey_json = instance.questionnaire_json_snapshot or {}
    answers = instance.answers_json if isinstance(instance.answers_json, dict) else {}
    metrics = instance.metrics_json if isinstance(instance.metrics_json, dict) else {}
    return render_to_string(
        "questionnaires/response_pdf.html",
        {
            "title": instance.questionnaire_type.title,
            "instance": instance,
            "questions": resolve_questions(survey_json, answers),
            "metrics": resolve_metrics(survey_json, metrics),
        },
    )


def generate_response_pdf(instance: Questionnaire) -> bytes:
    # Imported here so the rest of the app runs on machines without Pango.
    import weasyprint  # type: ignore[import-untyped]

    return weasyprint.HTML(string=render_response_html(instance)).write_pdf()
