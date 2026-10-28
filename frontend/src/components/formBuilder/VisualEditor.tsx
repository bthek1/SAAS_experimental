/**
 * VisualEditor — Phase 2 of PLAN-21.
 *
 * A fully editable visual view of a SurveyJS JSON object.
 * Every UI action produces a targeted patch via patchSurveyJson / spliceJsonArray;
 * the JSON is never rebuilt from scratch.
 *
 * The component is fully controlled: it receives the live surveyJson object and
 * calls onChange with a new object on every edit.  Unknown properties are
 * preserved (they are never read from or written by this component).
 */

import { useState, type ReactNode } from "react"
import { patchSurveyJson, spliceJsonArray, type JsonPath } from "@/lib/surveyPatch"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import type { SurveyJson } from "@/types/questionnaires"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Json = Record<string, unknown>
type Path = JsonPath

// Properties explicitly rendered by the visual editor per element type.
// Anything not listed here appears in the "Other properties" section.
const COMMON_KNOWN_PROPS = new Set([
  "type",
  "name",
  "title",
  "isRequired",
  "description",
  "visibleIf",
])

const TYPE_EXTRA_PROPS: Record<string, string[]> = {
  radiogroup: ["choices", "colCount"],
  checkbox: ["choices", "colCount"],
  dropdown: ["choices"],
  tagbox: ["choices"],
  rating: ["rateMin", "rateMax"],
  text: ["inputType"],
  html: ["html"],
  expression: ["expression"],
  boolean: [],
  comment: [],
}

// These types are too complex for surgical inline editing; show a badge instead.
const COMPLEX_TYPES = new Set([
  "imagepicker",
  "multipletext",
  "matrix",
  "matrixdropdown",
  "matrixdynamic",
  "panel",
  "paneldynamic",
])

const KNOWN_SIMPLE_TYPES = new Set(Object.keys(TYPE_EXTRA_PROPS))

// Top-level survey properties explicitly rendered by SurveySettings.
// Any survey-level key outside this set triggers the "unknown properties" badge.
const KNOWN_SURVEY_PROPS = new Set([
  "title",
  "description",
  "locale",
  "showProgressBar",
  "showQuestionNumbers",
  "checkErrorsMode",
  "completedHtml",
  "pages",
  "elements",
])

// ---------------------------------------------------------------------------
// VisualEditor
// ---------------------------------------------------------------------------

export interface VisualEditorProps {
  surveyJson: SurveyJson
  onChange: (next: SurveyJson) => void
}

export function VisualEditor({ surveyJson, onChange }: VisualEditorProps) {
  function patch(path: Path, value: unknown) {
    onChange(patchSurveyJson(surveyJson, path, value))
  }

  function splice(arrayPath: Path, index: number, deleteCount: number, ...items: unknown[]) {
    onChange(spliceJsonArray(surveyJson, arrayPath, index, deleteCount, ...items))
  }

  const isPaged = Array.isArray(surveyJson.pages)
  const pages: Json[] = isPaged
    ? (surveyJson.pages as Json[])
    : Array.isArray(surveyJson.elements)
      ? [{ name: "page1", elements: surveyJson.elements }]
      : [{ name: "page1", elements: [] }]

  function addPage() {
    const newPage: Json = { name: `page${pages.length + 1}`, elements: [] }
    splice(["pages"], pages.length, 0, newPage)
  }

  function movePage(pi: number, direction: -1 | 1) {
    const arr = [...(surveyJson.pages as Json[])]
    const target = pi + direction
    if (target < 0 || target >= arr.length) return
    ;[arr[pi], arr[target]] = [arr[target], arr[pi]]
    patch(["pages"], arr)
  }

  function deletePage(pi: number) {
    splice(["pages"], pi, 1)
  }

  function getElementsPath(pi: number): Path {
    return isPaged ? ["pages", pi, "elements"] : ["elements"]
  }

  function addElement(pi: number) {
    const elements =
      (isPaged ? (pages[pi]?.elements as Json[]) : (surveyJson.elements as Json[])) ?? []
    const newEl: Json = { type: "text", name: `question${elements.length + 1}`, title: "" }
    splice(getElementsPath(pi), elements.length, 0, newEl)
  }

  function deleteElement(pi: number, ei: number) {
    splice(getElementsPath(pi), ei, 1)
  }

  function moveElement(pi: number, ei: number, direction: -1 | 1) {
    const elemPath = getElementsPath(pi)
    const elements = Array.isArray(pages[pi]?.elements) ? [...(pages[pi].elements as Json[])] : []
    const target = ei + direction
    if (target < 0 || target >= elements.length) return
    ;[elements[ei], elements[target]] = [elements[target], elements[ei]]
    patch(elemPath, elements)
  }

  function patchElement(pi: number, ei: number, subPath: Path, value: unknown) {
    const base: Path = isPaged
      ? ["pages", pi, "elements", ei, ...subPath]
      : ["elements", ei, ...subPath]
    patch(base, value)
  }

  const hasUnknownSurveyProps = Object.keys(surveyJson).some((k) => !KNOWN_SURVEY_PROPS.has(k))

  return (
    <div data-testid="survey-outline" className="space-y-4 overflow-auto border-r p-4">
      {/* Info badge shown only when the survey contains unknown top-level properties */}
      {hasUnknownSurveyProps && (
        <div
          data-testid="unknown-props-badge"
          className="rounded-md border border-border bg-muted px-3 py-2 text-xs text-muted-foreground"
        >
          Unknown properties are preserved but not shown here. Use JSON mode to edit them.
        </div>
      )}

      {/* Survey-level settings */}
      <SurveySettings surveyJson={surveyJson} onPatch={patch} />

      {/* Pages */}
      {pages.map((page, pi) => {
        const elements: Json[] = Array.isArray(page.elements) ? (page.elements as Json[]) : []

        return (
          <div
            key={pi}
            data-testid={`page-editor-${pi}`}
            className="rounded-lg border border-border p-3 space-y-3"
          >
            {/* Page header */}
            <div className="flex items-center gap-2">
              {isPaged ? (
                <Input
                  value={typeof page.title === "string" ? page.title : ""}
                  onChange={(e) => patch(["pages", pi, "title"], e.target.value || undefined)}
                  placeholder={typeof page.name === "string" ? page.name : `page${pi + 1}`}
                  className="h-7 flex-1 text-sm font-medium"
                  aria-label={`Page ${pi + 1} title`}
                />
              ) : (
                <span className="text-sm font-semibold text-muted-foreground">Questions</span>
              )}
              {isPaged && (
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    type="button"
                    onClick={() => movePage(pi, -1)}
                    disabled={pi === 0}
                    aria-label="Move page up"
                    className="rounded px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-muted disabled:opacity-30"
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    onClick={() => movePage(pi, 1)}
                    disabled={pi === pages.length - 1}
                    aria-label="Move page down"
                    className="rounded px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-muted disabled:opacity-30"
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    onClick={() => deletePage(pi)}
                    disabled={pages.length <= 1}
                    aria-label="Delete page"
                    className="rounded px-1.5 py-0.5 text-xs text-destructive hover:bg-destructive/10 disabled:opacity-30"
                  >
                    ✕
                  </button>
                </div>
              )}
            </div>

            {/* Elements */}
            {elements.length === 0 ? (
              <p className="text-sm italic text-muted-foreground">No questions on this page</p>
            ) : (
              <ul className="space-y-2">
                {elements.map((el, ei) => (
                  <ElementEditor
                    key={ei}
                    element={el}
                    elementIndex={ei}
                    totalElements={elements.length}
                    onPatch={(subPath, value) => patchElement(pi, ei, subPath, value)}
                    onDelete={() => deleteElement(pi, ei)}
                    onMove={(dir) => moveElement(pi, ei, dir)}
                  />
                ))}
              </ul>
            )}

            <Button
              size="sm"
              variant="outline"
              onClick={() => addElement(pi)}
              data-testid={`add-question-btn-${pi}`}
            >
              + Add question
            </Button>
          </div>
        )
      })}

      {/* Add page button — only for paged surveys */}
      {isPaged && (
        <Button size="sm" variant="outline" onClick={addPage} data-testid="add-page-btn">
          + Add page
        </Button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// SurveySettings
// ---------------------------------------------------------------------------

interface SurveySettingsProps {
  surveyJson: Json
  onPatch: (path: Path, value: unknown) => void
}

function SurveySettings({ surveyJson, onPatch }: SurveySettingsProps) {
  const [expanded, setExpanded] = useState(true)

  const progressBar =
    typeof surveyJson.showProgressBar === "string" ? surveyJson.showProgressBar : ""
  const questionNumbers =
    surveyJson.showQuestionNumbers === false
      ? "off"
      : typeof surveyJson.showQuestionNumbers === "string"
        ? surveyJson.showQuestionNumbers
        : ""

  return (
    <div data-testid="survey-settings" className="rounded-lg border border-border">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between p-3 text-left"
        aria-expanded={expanded}
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Survey Settings
        </span>
        <span className="text-xs text-muted-foreground">{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div className="space-y-3 border-t border-border p-3">
          <FieldRow label="Title">
            <Input
              data-testid="survey-title-input"
              value={typeof surveyJson.title === "string" ? surveyJson.title : ""}
              onChange={(e) => onPatch(["title"], e.target.value || undefined)}
              placeholder="Survey title"
              className="h-8 text-sm"
            />
          </FieldRow>

          <FieldRow label="Description">
            <Textarea
              data-testid="survey-description-input"
              value={typeof surveyJson.description === "string" ? surveyJson.description : ""}
              onChange={(e) => onPatch(["description"], e.target.value || undefined)}
              placeholder="Optional description"
              rows={2}
              className="text-sm"
            />
          </FieldRow>

          <div className="flex flex-wrap gap-3">
            <FieldRow label="Locale">
              <Input
                value={typeof surveyJson.locale === "string" ? surveyJson.locale : ""}
                onChange={(e) => onPatch(["locale"], e.target.value || undefined)}
                placeholder="e.g. en"
                className="h-8 w-24 text-sm"
              />
            </FieldRow>

            <FieldRow label="Progress bar">
              <select
                value={progressBar}
                onChange={(e) => onPatch(["showProgressBar"], e.target.value || undefined)}
                className="h-8 rounded border border-border bg-background px-2 text-sm"
              >
                <option value="">Off</option>
                <option value="top">Top</option>
                <option value="bottom">Bottom</option>
                <option value="both">Both</option>
              </select>
            </FieldRow>

            <FieldRow label="Question numbers">
              <select
                value={questionNumbers}
                onChange={(e) => {
                  const v = e.target.value
                  onPatch(["showQuestionNumbers"], v === "" ? undefined : v === "off" ? false : v)
                }}
                className="h-8 rounded border border-border bg-background px-2 text-sm"
              >
                <option value="">Default (on)</option>
                <option value="off">Off</option>
                <option value="onPage">Per page</option>
              </select>
            </FieldRow>
          </div>

          <FieldRow label="Completion HTML">
            <Textarea
              value={typeof surveyJson.completedHtml === "string" ? surveyJson.completedHtml : ""}
              onChange={(e) => onPatch(["completedHtml"], e.target.value || undefined)}
              placeholder="HTML shown after submission"
              rows={2}
              className="text-sm"
            />
          </FieldRow>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ElementEditor
// ---------------------------------------------------------------------------

interface ElementEditorProps {
  element: Json
  elementIndex: number
  totalElements: number
  onPatch: (path: Path, value: unknown) => void
  onDelete: () => void
  onMove: (direction: -1 | 1) => void
}

function ElementEditor({
  element,
  elementIndex,
  totalElements,
  onPatch,
  onDelete,
  onMove,
}: ElementEditorProps) {
  const [expanded, setExpanded] = useState(false)

  const elType = typeof element.type === "string" ? element.type : "text"
  const elName = typeof element.name === "string" ? element.name : `element${elementIndex + 1}`
  const elTitle = typeof element.title === "string" ? element.title : ""
  const isComplex = COMPLEX_TYPES.has(elType)
  const isKnown = KNOWN_SIMPLE_TYPES.has(elType)

  return (
    <li data-testid={`element-editor-${elementIndex}`} className="rounded-lg border border-border">
      {/* Header row */}
      <div className="flex items-center gap-2 p-2">
        {/* Reorder */}
        <div className="flex flex-col shrink-0">
          <button
            type="button"
            onClick={() => onMove(-1)}
            disabled={elementIndex === 0}
            aria-label="Move question up"
            className="rounded px-1 text-xs text-muted-foreground hover:bg-muted disabled:opacity-30 leading-4"
          >
            ▲
          </button>
          <button
            type="button"
            onClick={() => onMove(1)}
            disabled={elementIndex === totalElements - 1}
            aria-label="Move question down"
            className="rounded px-1 text-xs text-muted-foreground hover:bg-muted disabled:opacity-30 leading-4"
          >
            ▼
          </button>
        </div>

        {/* Type badge */}
        <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
          {elType}
        </span>

        {/* Expand button */}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex-1 text-left text-sm font-medium"
          aria-expanded={expanded}
          data-testid={`element-expand-btn-${elementIndex}`}
        >
          {elTitle || elName}
          {elTitle && elTitle !== elName && (
            <span className="ml-1 text-xs text-muted-foreground">({elName})</span>
          )}
        </button>

        {/* Delete */}
        <button
          type="button"
          onClick={onDelete}
          aria-label="Delete question"
          className="shrink-0 rounded px-1.5 py-0.5 text-xs text-destructive hover:bg-destructive/10"
        >
          ✕
        </button>
      </div>

      {/* Edit fields (when expanded) */}
      {expanded && (
        <div className="space-y-3 border-t border-border p-3">
          {isComplex ? (
            /* Complex type — show a read-only badge */
            <p
              data-testid={`complex-type-badge-${elementIndex}`}
              className={cn("rounded bg-muted p-2 text-xs text-muted-foreground")}
            >
              <span className="font-semibold">{elType}</span>
              {" — Use JSON mode to edit this question type."}
            </p>
          ) : (
            <>
              {/* Common fields */}
              <FieldRow label="Title">
                <Input
                  data-testid={`element-title-input-${elementIndex}`}
                  value={elTitle}
                  onChange={(e) => onPatch(["title"], e.target.value || undefined)}
                  placeholder="Question title"
                  className="h-8 text-sm"
                />
              </FieldRow>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id={`req-${elName}-${elementIndex}`}
                  data-testid={`element-required-checkbox-${elementIndex}`}
                  checked={element.isRequired === true}
                  onChange={(e) => onPatch(["isRequired"], e.target.checked || undefined)}
                  className="h-4 w-4"
                />
                <label htmlFor={`req-${elName}-${elementIndex}`} className="text-sm">
                  Required
                </label>
              </div>

              <FieldRow label="Description">
                <Textarea
                  value={typeof element.description === "string" ? element.description : ""}
                  onChange={(e) => onPatch(["description"], e.target.value || undefined)}
                  placeholder="Optional hint / description"
                  rows={2}
                  className="text-sm"
                />
              </FieldRow>

              <FieldRow label="Visible if">
                <Input
                  value={typeof element.visibleIf === "string" ? element.visibleIf : ""}
                  onChange={(e) => onPatch(["visibleIf"], e.target.value || undefined)}
                  placeholder="{question} = 'value'"
                  className="h-8 font-mono text-sm"
                />
              </FieldRow>

              {/* Type-specific controls */}
              {isKnown && (
                <TypeSpecificControls element={element} elType={elType} onPatch={onPatch} />
              )}
            </>
          )}

          {/* Unknown / other properties — read-only, always shown */}
          <OtherProperties element={element} elType={elType} />
        </div>
      )}
    </li>
  )
}

// ---------------------------------------------------------------------------
// TypeSpecificControls
// ---------------------------------------------------------------------------

interface TypeSpecificControlsProps {
  element: Json
  elType: string
  onPatch: (path: Path, value: unknown) => void
}

function TypeSpecificControls({ element, elType, onPatch }: TypeSpecificControlsProps) {
  if (["radiogroup", "checkbox", "dropdown", "tagbox"].includes(elType)) {
    const hasColCount = elType === "radiogroup" || elType === "checkbox"
    return (
      <div className="space-y-3">
        <ChoicesControl element={element} onPatch={onPatch} />
        {hasColCount && (
          <FieldRow label="Layout (columns)">
            <select
              value={typeof element.colCount === "number" ? element.colCount : 0}
              onChange={(e) => onPatch(["colCount"], Number(e.target.value) || undefined)}
              className="h-8 rounded border border-border bg-background px-2 text-sm"
            >
              <option value={0}>Vertical</option>
              <option value={-1}>Horizontal row</option>
              <option value={2}>2 columns</option>
              <option value={3}>3 columns</option>
              <option value={4}>4 columns</option>
            </select>
          </FieldRow>
        )}
      </div>
    )
  }

  if (elType === "rating") {
    return (
      <div className="flex gap-3">
        <FieldRow label="Min rating">
          <Input
            type="number"
            value={typeof element.rateMin === "number" ? element.rateMin : 1}
            onChange={(e) => onPatch(["rateMin"], Number(e.target.value))}
            className="h-8 w-20 text-sm"
          />
        </FieldRow>
        <FieldRow label="Max rating">
          <Input
            type="number"
            value={typeof element.rateMax === "number" ? element.rateMax : 5}
            onChange={(e) => onPatch(["rateMax"], Number(e.target.value))}
            className="h-8 w-20 text-sm"
          />
        </FieldRow>
      </div>
    )
  }

  if (elType === "text") {
    const TEXT_INPUT_TYPES = [
      "text",
      "number",
      "email",
      "date",
      "datetime-local",
      "time",
      "tel",
      "url",
      "password",
      "range",
      "color",
    ]
    return (
      <FieldRow label="Input type">
        <select
          value={typeof element.inputType === "string" ? element.inputType : "text"}
          onChange={(e) =>
            onPatch(["inputType"], e.target.value === "text" ? undefined : e.target.value)
          }
          className="h-8 rounded border border-border bg-background px-2 text-sm"
        >
          {TEXT_INPUT_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </FieldRow>
    )
  }

  if (elType === "html") {
    return (
      <FieldRow label="HTML content">
        <Textarea
          value={typeof element.html === "string" ? element.html : ""}
          onChange={(e) => onPatch(["html"], e.target.value || undefined)}
          placeholder="<p>Content</p>"
          rows={3}
          className="font-mono text-sm"
        />
      </FieldRow>
    )
  }

  if (elType === "expression") {
    return (
      <FieldRow label="Expression">
        <Input
          value={typeof element.expression === "string" ? element.expression : ""}
          onChange={(e) => onPatch(["expression"], e.target.value || undefined)}
          placeholder="{q1} + {q2}"
          className="h-8 font-mono text-sm"
        />
      </FieldRow>
    )
  }

  // boolean, comment — no extra fields beyond common ones
  return null
}

// ---------------------------------------------------------------------------
// ChoicesControl
// ---------------------------------------------------------------------------

interface ChoicesControlProps {
  element: Json
  onPatch: (path: Path, value: unknown) => void
}

function choicesToText(choices: unknown[]): string {
  return choices
    .map((c) => {
      if (typeof c === "string") return c
      if (c && typeof c === "object" && "value" in c) {
        const obj = c as { value: string; text?: string }
        return obj.text ? `${obj.value} | ${obj.text}` : obj.value
      }
      return JSON.stringify(c)
    })
    .join("\n")
}

function textToChoices(text: string): unknown[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      if (line.includes(" | ")) {
        const idx = line.indexOf(" | ")
        const value = line.slice(0, idx).trim()
        const label = line.slice(idx + 3).trim()
        return { value, text: label }
      }
      return line
    })
}

function ChoicesControl({ element, onPatch }: ChoicesControlProps) {
  const choices: unknown[] = Array.isArray(element.choices) ? element.choices : []

  return (
    <FieldRow label="Choices — one per line, or 'value | Label'">
      <Textarea
        data-testid="choices-textarea"
        value={choicesToText(choices)}
        onChange={(e) => onPatch(["choices"], textToChoices(e.target.value))}
        placeholder={"Option 1\nOption 2\nopt_val | Option label"}
        rows={4}
        className="text-sm"
      />
    </FieldRow>
  )
}

// ---------------------------------------------------------------------------
// OtherProperties
// ---------------------------------------------------------------------------

interface OtherPropertiesProps {
  element: Json
  elType: string
}

function OtherProperties({ element, elType }: OtherPropertiesProps) {
  const [expanded, setExpanded] = useState(false)

  const extraProps = new Set(TYPE_EXTRA_PROPS[elType] ?? [])
  const knownProps = new Set([...COMMON_KNOWN_PROPS, ...extraProps])
  const otherEntries = Object.entries(element).filter(([k]) => !knownProps.has(k))

  if (otherEntries.length === 0) return null

  return (
    <div data-testid="other-properties" className="rounded border border-border">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-1.5 text-left text-xs text-muted-foreground"
        aria-expanded={expanded}
      >
        <span>Other properties ({otherEntries.length})</span>
        <span>{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div className="space-y-1 border-t border-border p-3">
          <p className="mb-2 text-xs text-muted-foreground">
            These properties are preserved but not editable here. Use JSON mode to modify them.
          </p>
          {otherEntries.map(([k, v]) => (
            <div key={k} className="flex gap-2 text-xs font-mono">
              <span className="shrink-0 text-muted-foreground">{k}:</span>
              <span className="truncate">{JSON.stringify(v)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// FieldRow — label + control layout helper
// ---------------------------------------------------------------------------

interface FieldRowProps {
  label: string
  children: ReactNode
}

function FieldRow({ label, children }: FieldRowProps) {
  return (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground">{label}</p>
      {children}
    </div>
  )
}
