import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { SUPPORTED_TYPES } from "@/lib/formBuilder"
import type {
  BuilderQuestion,
  ChoiceItem,
  FieldType,
  ImagePickerChoice,
  MatrixColumn,
  MatrixEntry,
  MultipleTextItem,
  AnyQuestion,
} from "@/lib/formBuilder"
import { ChoicesEditor } from "./ChoicesEditor"

const TYPE_LABELS: Record<FieldType, string> = {
  text: "Short text",
  comment: "Long text",
  radiogroup: "Single choice",
  checkbox: "Multiple choice",
  dropdown: "Dropdown",
  rating: "Rating scale",
  boolean: "Yes / No",
  tagbox: "Tag box (multi-select dropdown)",
  imagepicker: "Image picker",
  multipletext: "Multiple text inputs",
  html: "HTML content",
  expression: "Expression / calculated value",
  matrix: "Matrix (single choice rows)",
  matrixdropdown: "Matrix dropdown",
  matrixdynamic: "Matrix dynamic (add rows)",
  panel: "Panel (group)",
  paneldynamic: "Panel dynamic (repeating)",
}

// Value -> label maps so the Base UI <SelectValue> shows the label, not the raw value.
const COL_COUNT_LABELS: Record<string, string> = {
  "0": "Horizontal (row)",
  "2": "2 columns",
  "3": "3 columns",
  "1": "Vertical (default)",
}
const RATE_TYPE_LABELS: Record<string, string> = {
  numbers: "Numbers",
  stars: "Stars",
  smileys: "Smileys",
}
const DISPLAY_STYLE_LABELS: Record<string, string> = {
  none: "None",
  decimal: "Decimal",
  currency: "Currency",
  percent: "Percent",
}

const CHOICE_TYPES: FieldType[] = ["radiogroup", "checkbox", "dropdown", "tagbox"]
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

interface QuestionEditorProps {
  question: BuilderQuestion
  onChange: (updated: BuilderQuestion) => void
  /** Whether another question already uses the same name */
  duplicateName?: boolean
}

export function QuestionEditor({ question, onChange, duplicateName }: QuestionEditorProps) {
  function update(patch: Partial<BuilderQuestion>) {
    onChange({ ...question, ...patch })
  }

  function handleTypeChange(newType: FieldType) {
    const patch: Partial<BuilderQuestion> = { type: newType }
    if (CHOICE_TYPES.includes(newType) && !question.choices) {
      patch.choices = []
    }
    if ((newType === "radiogroup" || newType === "checkbox") && question.colCount === undefined) {
      patch.colCount = 0
    }
    if (newType === "rating") {
      patch.rateMin = question.rateMin ?? 1
      patch.rateMax = question.rateMax ?? 5
    }
    if (newType === "multipletext" && !question.items) {
      patch.items = []
    }
    if (newType === "matrix" && !question.rows_) {
      patch.rows_ = []
      patch.columns = []
    }
    if ((newType === "matrixdropdown" || newType === "matrixdynamic") && !question.matrixColumns) {
      patch.rows_ = []
      patch.matrixColumns = []
    }
    if (newType === "panel" && !question.panelElements) {
      patch.panelElements = []
    }
    if (newType === "paneldynamic" && !question.templateElements) {
      patch.templateElements = []
    }
    update(patch)
  }

  const showChoices = CHOICE_TYPES.includes(question.type)
  const showRating = question.type === "rating"
  const showBoolean = question.type === "boolean"
  const showComment = question.type === "comment"
  const showText = question.type === "text"
  const showHtml = question.type === "html"
  const showExpression = question.type === "expression"
  const showImagePicker = question.type === "imagepicker"
  const showMultipleText = question.type === "multipletext"
  const showMatrix = question.type === "matrix"
  const showMatrixDropdown = question.type === "matrixdropdown" || question.type === "matrixdynamic"
  const hasTitle = question.type !== "html"

  return (
    <div className="space-y-4 rounded-lg border border-border p-4">
      {/* Title */}
      {hasTitle && (
        <div className="space-y-1">
          <Label htmlFor="q-title">Question text</Label>
          <Input
            id="q-title"
            value={question.title}
            onChange={(e) => update({ title: e.target.value })}
            placeholder="Enter question text"
          />
        </div>
      )}

      {/* Description */}
      {hasTitle && (
        <div className="space-y-1">
          <Label htmlFor="q-description">Description (optional)</Label>
          <Input
            id="q-description"
            value={question.description ?? ""}
            onChange={(e) => update({ description: e.target.value || undefined })}
            placeholder="Shown below the question text"
          />
        </div>
      )}

      {/* Name (unique key) */}
      <div className="space-y-1">
        <Label htmlFor="q-name">Name (unique key)</Label>
        <Input
          id="q-name"
          value={question.name}
          onChange={(e) => update({ name: e.target.value })}
          placeholder="e.g. q1"
          aria-invalid={duplicateName || undefined}
        />
        {duplicateName && (
          <p className="text-xs text-destructive" data-testid="duplicate-name-error">
            This name is already used by another question.
          </p>
        )}
      </div>

      {/* Type */}
      <div className="space-y-1">
        <Label>Type</Label>
        <Select
          value={question.type}
          items={TYPE_LABELS}
          onValueChange={(v) => {
            if (v !== null) handleTypeChange(v)
          }}
        >
          <SelectTrigger data-testid="type-select">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SUPPORTED_TYPES.map((t) => (
              <SelectItem key={t} value={t}>
                {TYPE_LABELS[t]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Required */}
      {hasTitle && (
        <div className="flex items-center gap-2">
          <input
            id="q-required"
            type="checkbox"
            checked={question.required}
            onChange={(e) => update({ required: e.target.checked })}
            className="h-4 w-4"
          />
          <Label htmlFor="q-required">Required</Label>
        </div>
      )}

      {/* Choices */}
      {showChoices && (
        <div className="space-y-1">
          <Label>Choices</Label>
          <ChoicesEditor
            choices={question.choices ?? []}
            onChange={(choices: ChoiceItem[]) => update({ choices })}
          />
          <div className="mt-2 flex flex-wrap gap-4">
            <div className="flex items-center gap-2">
              <input
                id="q-other"
                type="checkbox"
                checked={question.showOtherItem ?? false}
                onChange={(e) => update({ showOtherItem: e.target.checked || undefined })}
                className="h-4 w-4"
              />
              <Label htmlFor="q-other">Show "Other" option</Label>
            </div>
            {(question.type === "radiogroup" || question.type === "checkbox") && (
              <div className="flex items-center gap-2">
                <input
                  id="q-none"
                  type="checkbox"
                  checked={question.showNoneItem ?? false}
                  onChange={(e) => update({ showNoneItem: e.target.checked || undefined })}
                  className="h-4 w-4"
                />
                <Label htmlFor="q-none">Show "None" option</Label>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Layout — colCount for radiogroup / checkbox */}
      {(question.type === "radiogroup" || question.type === "checkbox") && (
        <div className="space-y-1">
          <Label htmlFor="q-col-count">Layout</Label>
          <Select
            value={String(question.colCount ?? 0)}
            items={COL_COUNT_LABELS}
            onValueChange={(v) => {
              if (v !== null) update({ colCount: Number(v) })
            }}
          >
            <SelectTrigger id="q-col-count" data-testid="col-count-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(COL_COUNT_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Rating */}
      {showRating && (
        <>
          <div className="flex gap-4">
            <div className="flex-1 space-y-1">
              <Label htmlFor="q-rate-min">Min</Label>
              <Input
                id="q-rate-min"
                type="number"
                value={question.rateMin ?? 1}
                onChange={(e) => update({ rateMin: Number(e.target.value) })}
                data-testid="rate-min-input"
              />
            </div>
            <div className="flex-1 space-y-1">
              <Label htmlFor="q-rate-max">Max</Label>
              <Input
                id="q-rate-max"
                type="number"
                value={question.rateMax ?? 5}
                onChange={(e) => update({ rateMax: Number(e.target.value) })}
                data-testid="rate-max-input"
              />
            </div>
            <div className="flex-1 space-y-1">
              <Label htmlFor="q-rate-step">Step</Label>
              <Input
                id="q-rate-step"
                type="number"
                value={question.rateStep ?? ""}
                onChange={(e) =>
                  update({ rateStep: e.target.value ? Number(e.target.value) : undefined })
                }
                placeholder="1"
                data-testid="rate-step-input"
              />
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="q-rate-type">Display style</Label>
            <Select
              value={question.rateType ?? "numbers"}
              items={RATE_TYPE_LABELS}
              onValueChange={(v) => {
                if (v !== null) update({ rateType: v })
              }}
            >
              <SelectTrigger id="q-rate-type" data-testid="rate-type-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(RATE_TYPE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex gap-4">
            <div className="flex-1 space-y-1">
              <Label htmlFor="q-min-desc">Min label</Label>
              <Input
                id="q-min-desc"
                value={question.minRateDescription ?? ""}
                onChange={(e) => update({ minRateDescription: e.target.value || undefined })}
                placeholder="e.g. Poor"
              />
            </div>
            <div className="flex-1 space-y-1">
              <Label htmlFor="q-max-desc">Max label</Label>
              <Input
                id="q-max-desc"
                value={question.maxRateDescription ?? ""}
                onChange={(e) => update({ maxRateDescription: e.target.value || undefined })}
                placeholder="e.g. Excellent"
              />
            </div>
          </div>
        </>
      )}

      {/* Boolean labels */}
      {showBoolean && (
        <div className="flex gap-4">
          <div className="flex-1 space-y-1">
            <Label htmlFor="q-label-true">True label</Label>
            <Input
              id="q-label-true"
              value={question.labelTrue ?? ""}
              onChange={(e) => update({ labelTrue: e.target.value || undefined })}
              placeholder="Yes"
              data-testid="label-true-input"
            />
          </div>
          <div className="flex-1 space-y-1">
            <Label htmlFor="q-label-false">False label</Label>
            <Input
              id="q-label-false"
              value={question.labelFalse ?? ""}
              onChange={(e) => update({ labelFalse: e.target.value || undefined })}
              placeholder="No"
              data-testid="label-false-input"
            />
          </div>
        </div>
      )}

      {/* Comment options */}
      {showComment && (
        <div className="flex gap-4">
          <div className="flex-1 space-y-1">
            <Label htmlFor="q-rows">Rows</Label>
            <Input
              id="q-rows"
              type="number"
              value={question.rows ?? ""}
              onChange={(e) =>
                update({ rows: e.target.value ? Number(e.target.value) : undefined })
              }
              placeholder="4"
              data-testid="comment-rows-input"
            />
          </div>
          <div className="flex-1 space-y-1">
            <Label htmlFor="q-placeholder">Placeholder</Label>
            <Input
              id="q-placeholder"
              value={question.placeholder ?? ""}
              onChange={(e) => update({ placeholder: e.target.value || undefined })}
              placeholder="Enter placeholder text"
              data-testid="comment-placeholder-input"
            />
          </div>
        </div>
      )}

      {/* Text input options */}
      {showText && (
        <>
          <div className="space-y-1">
            <Label htmlFor="q-input-type">Input type</Label>
            <Select
              value={question.inputType ?? "text"}
              onValueChange={(v) => {
                if (v !== null) update({ inputType: v === "text" ? undefined : v })
              }}
            >
              <SelectTrigger id="q-input-type" data-testid="input-type-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TEXT_INPUT_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="q-text-placeholder">Placeholder</Label>
            <Input
              id="q-text-placeholder"
              value={question.placeholder ?? ""}
              onChange={(e) => update({ placeholder: e.target.value || undefined })}
              placeholder="Placeholder text"
              data-testid="text-placeholder-input"
            />
          </div>
          {(question.inputType === "number" ||
            question.inputType === "range" ||
            question.inputType === "date") && (
            <div className="flex gap-4">
              <div className="flex-1 space-y-1">
                <Label htmlFor="q-min">Min</Label>
                <Input
                  id="q-min"
                  value={question.min ?? ""}
                  onChange={(e) => update({ min: e.target.value || undefined })}
                  placeholder="min"
                  data-testid="text-min-input"
                />
              </div>
              <div className="flex-1 space-y-1">
                <Label htmlFor="q-max">Max</Label>
                <Input
                  id="q-max"
                  value={question.max ?? ""}
                  onChange={(e) => update({ max: e.target.value || undefined })}
                  placeholder="max"
                  data-testid="text-max-input"
                />
              </div>
              <div className="flex-1 space-y-1">
                <Label htmlFor="q-step">Step</Label>
                <Input
                  id="q-step"
                  type="number"
                  value={question.step ?? ""}
                  onChange={(e) =>
                    update({ step: e.target.value ? Number(e.target.value) : undefined })
                  }
                  placeholder="step"
                  data-testid="text-step-input"
                />
              </div>
            </div>
          )}
          <div className="space-y-1">
            <Label>Validators</Label>
            <div className="flex flex-wrap gap-3">
              {(["email", "numeric", "text", "regex"] as const).map((vtype) => {
                const has = question.validators?.some((v) => v.type === vtype) ?? false
                return (
                  <div key={vtype} className="flex items-center gap-1">
                    <input
                      id={`q-validator-${vtype}`}
                      type="checkbox"
                      checked={has}
                      onChange={(e) => {
                        const current = question.validators ?? []
                        if (e.target.checked) {
                          update({ validators: [...current, { type: vtype }] })
                        } else {
                          const next = current.filter((v) => v.type !== vtype)
                          update({ validators: next.length ? next : undefined })
                        }
                      }}
                      className="h-4 w-4"
                    />
                    <Label htmlFor={`q-validator-${vtype}`}>{vtype}</Label>
                  </div>
                )
              })}
            </div>
          </div>
        </>
      )}

      {/* HTML content */}
      {showHtml && (
        <div className="space-y-1">
          <Label htmlFor="q-html">HTML content</Label>
          <Textarea
            id="q-html"
            value={question.html ?? ""}
            onChange={(e) => update({ html: e.target.value || undefined })}
            rows={5}
            placeholder="<p>Enter HTML here</p>"
            data-testid="html-content-textarea"
          />
        </div>
      )}

      {/* Expression */}
      {showExpression && (
        <>
          <div className="space-y-1">
            <Label htmlFor="q-expression">Expression</Label>
            <Input
              id="q-expression"
              value={question.expression ?? ""}
              onChange={(e) => update({ expression: e.target.value || undefined })}
              placeholder="{q1} + {q2}"
              data-testid="expression-input"
            />
          </div>
          <div className="flex gap-4">
            <div className="flex-1 space-y-1">
              <Label htmlFor="q-display-style">Display style</Label>
              <Select
                value={question.displayStyle ?? "none"}
                items={DISPLAY_STYLE_LABELS}
                onValueChange={(v) => {
                  if (v !== null) update({ displayStyle: v === "none" ? undefined : v })
                }}
              >
                <SelectTrigger id="q-display-style" data-testid="display-style-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(DISPLAY_STYLE_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex-1 space-y-1">
              <Label htmlFor="q-suffix">Suffix</Label>
              <Input
                id="q-suffix"
                value={question.suffix ?? ""}
                onChange={(e) => update({ suffix: e.target.value || undefined })}
                placeholder="e.g. pts"
              />
            </div>
            <div className="flex-1 space-y-1">
              <Label htmlFor="q-prefix">Prefix</Label>
              <Input
                id="q-prefix"
                value={question.prefix ?? ""}
                onChange={(e) => update({ prefix: e.target.value || undefined })}
                placeholder="e.g. $"
              />
            </div>
          </div>
        </>
      )}

      {/* Image picker */}
      {showImagePicker && (
        <>
          <div className="space-y-1">
            <Label>Image choices</Label>
            <ImagePickerEditor
              choices={question.imagePickerChoices ?? []}
              onChange={(imagePickerChoices: ImagePickerChoice[]) => update({ imagePickerChoices })}
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              id="q-multiselect"
              type="checkbox"
              checked={question.multiSelect ?? false}
              onChange={(e) => update({ multiSelect: e.target.checked || undefined })}
              className="h-4 w-4"
            />
            <Label htmlFor="q-multiselect">Multi-select</Label>
          </div>
          <div className="flex gap-4">
            <div className="flex-1 space-y-1">
              <Label htmlFor="q-img-w">Image width (px)</Label>
              <Input
                id="q-img-w"
                type="number"
                value={question.imageWidth ?? ""}
                onChange={(e) =>
                  update({ imageWidth: e.target.value ? Number(e.target.value) : undefined })
                }
              />
            </div>
            <div className="flex-1 space-y-1">
              <Label htmlFor="q-img-h">Image height (px)</Label>
              <Input
                id="q-img-h"
                type="number"
                value={question.imageHeight ?? ""}
                onChange={(e) =>
                  update({ imageHeight: e.target.value ? Number(e.target.value) : undefined })
                }
              />
            </div>
          </div>
        </>
      )}

      {/* Multiple text */}
      {showMultipleText && (
        <div className="space-y-1">
          <Label>Sub-fields</Label>
          <MultipleTextEditor
            items={question.items ?? []}
            onChange={(items: MultipleTextItem[]) => update({ items })}
          />
        </div>
      )}

      {/* Matrix (simple) */}
      {showMatrix && (
        <>
          <div className="space-y-1">
            <Label>Rows</Label>
            <MatrixEntriesEditor
              entries={question.rows_ ?? []}
              onChange={(rows_: MatrixEntry[]) => update({ rows_ })}
              addLabel="+ Add row"
              testPrefix="matrix-row"
            />
          </div>
          <div className="space-y-1">
            <Label>Columns</Label>
            <MatrixEntriesEditor
              entries={question.columns ?? []}
              onChange={(columns: MatrixEntry[]) => update({ columns })}
              addLabel="+ Add column"
              testPrefix="matrix-col"
            />
          </div>
        </>
      )}

      {/* Matrix dropdown / dynamic */}
      {showMatrixDropdown && (
        <>
          <div className="space-y-1">
            <Label>Rows</Label>
            <MatrixEntriesEditor
              entries={question.rows_ ?? []}
              onChange={(rows_: MatrixEntry[]) => update({ rows_ })}
              addLabel="+ Add row"
              testPrefix="matrix-row"
            />
          </div>
          <div className="space-y-1">
            <Label>Columns</Label>
            <MatrixColumnsEditor
              columns={question.matrixColumns ?? []}
              onChange={(matrixColumns: MatrixColumn[]) => update({ matrixColumns })}
            />
          </div>
          {question.type === "matrixdynamic" && (
            <div className="flex gap-4">
              <div className="flex-1 space-y-1">
                <Label htmlFor="q-row-count">Initial row count</Label>
                <Input
                  id="q-row-count"
                  type="number"
                  value={question.rowCount ?? ""}
                  onChange={(e) =>
                    update({ rowCount: e.target.value ? Number(e.target.value) : undefined })
                  }
                />
              </div>
              <div className="flex-1 space-y-1">
                <Label htmlFor="q-add-row-text">Add row text</Label>
                <Input
                  id="q-add-row-text"
                  value={question.addRowText ?? ""}
                  onChange={(e) => update({ addRowText: e.target.value || undefined })}
                />
              </div>
              <div className="flex-1 space-y-1">
                <Label htmlFor="q-remove-row-text">Remove row text</Label>
                <Input
                  id="q-remove-row-text"
                  value={question.removeRowText ?? ""}
                  onChange={(e) => update({ removeRowText: e.target.value || undefined })}
                />
              </div>
            </div>
          )}
        </>
      )}

      {/* Panel */}
      {question.type === "panel" && (
        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="q-panel-state">Panel state</Label>
            <select
              id="q-panel-state"
              className="w-full rounded border border-border bg-background px-2 py-1 text-sm"
              value={question.panelState ?? ""}
              onChange={(e) => update({ panelState: e.target.value || undefined })}
            >
              <option value="">Default (expanded)</option>
              <option value="collapsed">Collapsed</option>
              <option value="expanded">Expanded</option>
              <option value="firstExpanded">First expanded</option>
            </select>
          </div>
          <PanelElementsEditor
            questions={question.panelElements ?? []}
            onChange={(qs) => update({ panelElements: qs })}
            label="Panel questions"
          />
        </div>
      )}

      {/* Panel dynamic */}
      {question.type === "paneldynamic" && (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1">
              <Label htmlFor="q-panel-count">Initial count</Label>
              <Input
                id="q-panel-count"
                type="number"
                min={0}
                value={question.panelCount ?? 1}
                onChange={(e) => update({ panelCount: Number(e.target.value) })}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="q-min-panel">Min panels</Label>
              <Input
                id="q-min-panel"
                type="number"
                min={0}
                value={question.minPanelCount ?? ""}
                onChange={(e) =>
                  update({ minPanelCount: e.target.value ? Number(e.target.value) : undefined })
                }
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="q-max-panel">Max panels</Label>
              <Input
                id="q-max-panel"
                type="number"
                min={0}
                value={question.maxPanelCount ?? ""}
                onChange={(e) =>
                  update({ maxPanelCount: e.target.value ? Number(e.target.value) : undefined })
                }
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <Label htmlFor="q-panel-add-text">Add button text</Label>
              <Input
                id="q-panel-add-text"
                value={question.panelAddText ?? ""}
                onChange={(e) => update({ panelAddText: e.target.value || undefined })}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="q-panel-remove-text">Remove button text</Label>
              <Input
                id="q-panel-remove-text"
                value={question.panelRemoveText ?? ""}
                onChange={(e) => update({ panelRemoveText: e.target.value || undefined })}
              />
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="q-template-title">Panel title template</Label>
            <Input
              id="q-template-title"
              value={question.templateTitle ?? ""}
              placeholder="e.g. Item #{panelIndex}"
              onChange={(e) => update({ templateTitle: e.target.value || undefined })}
            />
          </div>
          <PanelElementsEditor
            questions={question.templateElements ?? []}
            onChange={(qs) => update({ templateElements: qs })}
            label="Template questions"
          />
        </div>
      )}

      {/* Conditional logic */}
      {hasTitle && (
        <details className="group">
          <summary className="cursor-pointer text-sm font-medium text-muted-foreground">
            Conditional logic ▸
          </summary>
          <div className="mt-3 space-y-3">
            <div className="space-y-1">
              <Label htmlFor="q-visible-if">Visible if</Label>
              <Input
                id="q-visible-if"
                value={question.visibleIf ?? ""}
                onChange={(e) => update({ visibleIf: e.target.value || undefined })}
                placeholder="{q1} = 'yes'"
                data-testid="visible-if-input"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="q-required-if">Required if</Label>
              <Input
                id="q-required-if"
                value={question.requiredIf ?? ""}
                onChange={(e) => update({ requiredIf: e.target.value || undefined })}
                placeholder="{q1} = 'yes'"
                data-testid="required-if-input"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="q-enable-if">Enable if</Label>
              <Input
                id="q-enable-if"
                value={question.enableIf ?? ""}
                onChange={(e) => update({ enableIf: e.target.value || undefined })}
                placeholder="{q1} = 'yes'"
                data-testid="enable-if-input"
              />
            </div>
          </div>
        </details>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-editors
// ---------------------------------------------------------------------------

function ImagePickerEditor({
  choices,
  onChange,
}: {
  choices: ImagePickerChoice[]
  onChange: (choices: ImagePickerChoice[]) => void
}) {
  function update(index: number, field: keyof ImagePickerChoice, val: string) {
    onChange(choices.map((c, i) => (i === index ? { ...c, [field]: val || undefined } : c)))
  }
  function add() {
    onChange([...choices, { value: "" }])
  }
  function remove(index: number) {
    onChange(choices.filter((_, i) => i !== index))
  }
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[1fr_1fr_1fr_auto] gap-x-2 text-xs font-medium text-muted-foreground">
        <span>Value</span>
        <span>Label</span>
        <span>Image URL</span>
        <span />
      </div>
      {choices.map((c, i) => (
        <div key={i} className="grid grid-cols-[1fr_1fr_1fr_auto] gap-x-2">
          <Input
            value={c.value}
            onChange={(e) => update(i, "value", e.target.value)}
            placeholder="value"
          />
          <Input
            value={c.text ?? ""}
            onChange={(e) => update(i, "text", e.target.value)}
            placeholder="label"
          />
          <Input
            value={c.imageLink ?? ""}
            onChange={(e) => update(i, "imageLink", e.target.value)}
            placeholder="https://..."
          />
          <Button variant="ghost" size="sm" onClick={() => remove(i)}>
            ✕
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={add}
        data-testid="imagepicker-add-row"
      >
        + Add image
      </Button>
    </div>
  )
}

function MultipleTextEditor({
  items,
  onChange,
}: {
  items: MultipleTextItem[]
  onChange: (items: MultipleTextItem[]) => void
}) {
  function update(index: number, patch: Partial<MultipleTextItem>) {
    onChange(items.map((item, i) => (i === index ? { ...item, ...patch } : item)))
  }
  function add() {
    onChange([...items, { name: "" }])
  }
  function remove(index: number) {
    onChange(items.filter((_, i) => i !== index))
  }
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[1fr_1fr_auto_auto] gap-x-2 text-xs font-medium text-muted-foreground">
        <span>Name</span>
        <span>Title</span>
        <span>Req.</span>
        <span />
      </div>
      {items.map((item, i) => (
        <div key={i} className="grid grid-cols-[1fr_1fr_auto_auto] items-center gap-x-2">
          <Input
            value={item.name}
            onChange={(e) => update(i, { name: e.target.value })}
            placeholder="name"
          />
          <Input
            value={item.title ?? ""}
            onChange={(e) => update(i, { title: e.target.value || undefined })}
            placeholder="title"
          />
          <input
            type="checkbox"
            checked={item.isRequired ?? false}
            onChange={(e) => update(i, { isRequired: e.target.checked || undefined })}
            className="h-4 w-4"
          />
          <Button variant="ghost" size="sm" onClick={() => remove(i)}>
            ✕
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={add}
        data-testid="multipletext-add-item"
      >
        + Add field
      </Button>
    </div>
  )
}

function MatrixEntriesEditor({
  entries,
  onChange,
  addLabel,
  testPrefix,
}: {
  entries: MatrixEntry[]
  onChange: (entries: MatrixEntry[]) => void
  addLabel: string
  testPrefix: string
}) {
  function update(index: number, field: "value" | "text", val: string) {
    onChange(entries.map((e, i) => (i === index ? { ...e, [field]: val || undefined } : e)))
  }
  function add() {
    onChange([...entries, { value: "" }])
  }
  function remove(index: number) {
    onChange(entries.filter((_, i) => i !== index))
  }
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[1fr_1fr_auto] gap-x-2 text-xs font-medium text-muted-foreground">
        <span>Value</span>
        <span>Label</span>
        <span />
      </div>
      {entries.map((e, i) => (
        <div key={i} className="grid grid-cols-[1fr_1fr_auto] gap-x-2">
          <Input
            value={e.value}
            onChange={(ev) => update(i, "value", ev.target.value)}
            placeholder="value"
            data-testid={`${testPrefix}-value-${i}`}
          />
          <Input
            value={e.text ?? ""}
            onChange={(ev) => update(i, "text", ev.target.value)}
            placeholder="label"
            data-testid={`${testPrefix}-text-${i}`}
          />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => remove(i)}
            data-testid={`${testPrefix}-remove-${i}`}
          >
            ✕
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={add}
        data-testid={`${testPrefix}-add`}
      >
        {addLabel}
      </Button>
    </div>
  )
}

function MatrixColumnsEditor({
  columns,
  onChange,
}: {
  columns: MatrixColumn[]
  onChange: (columns: MatrixColumn[]) => void
}) {
  function update(index: number, patch: Partial<MatrixColumn>) {
    onChange(columns.map((c, i) => (i === index ? { ...c, ...patch } : c)))
  }
  function add() {
    onChange([...columns, { name: "" }])
  }
  function remove(index: number) {
    onChange(columns.filter((_, i) => i !== index))
  }
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[1fr_1fr_1fr_auto] gap-x-2 text-xs font-medium text-muted-foreground">
        <span>Name</span>
        <span>Title</span>
        <span>Cell type</span>
        <span />
      </div>
      {columns.map((c, i) => (
        <div key={i} className="grid grid-cols-[1fr_1fr_1fr_auto] items-center gap-x-2">
          <Input
            value={c.name}
            onChange={(e) => update(i, { name: e.target.value })}
            placeholder="name"
          />
          <Input
            value={c.title ?? ""}
            onChange={(e) => update(i, { title: e.target.value || undefined })}
            placeholder="title"
          />
          <Select
            value={c.cellType ?? "default"}
            onValueChange={(v) => {
              if (v !== null) update(i, { cellType: v === "default" ? undefined : v })
            }}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="default">default</SelectItem>
              <SelectItem value="text">text</SelectItem>
              <SelectItem value="dropdown">dropdown</SelectItem>
              <SelectItem value="checkbox">checkbox</SelectItem>
              <SelectItem value="radiogroup">radiogroup</SelectItem>
              <SelectItem value="rating">rating</SelectItem>
              <SelectItem value="boolean">boolean</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="ghost" size="sm" onClick={() => remove(i)}>
            ✕
          </Button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={add} data-testid="matrix-col-add">
        + Add column
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// PanelElementsEditor — simple inline list for panel/paneldynamic children
// ---------------------------------------------------------------------------

function PanelElementsEditor({
  questions,
  onChange,
  label,
}: {
  questions: AnyQuestion[]
  onChange: (qs: AnyQuestion[]) => void
  label: string
}) {
  const add = () => {
    const names = questions.map((q) => ("name" in q ? (q as BuilderQuestion).name : ""))
    const name = `question${questions.length + 1}`
    const unique = names.includes(name) ? `${name}_1` : name
    const newQ: BuilderQuestion = { name: unique, title: "", type: "text", required: false }
    onChange([...questions, newQ])
  }

  const remove = (i: number) => {
    const updated = questions.filter((_, idx) => idx !== i)
    onChange(updated)
  }

  const update = (i: number, patch: Partial<BuilderQuestion>) => {
    const updated = questions.map((q, idx) =>
      idx === i ? ({ ...(q as BuilderQuestion), ...patch } as AnyQuestion) : q,
    )
    onChange(updated)
  }

  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {questions.map((q, i) => {
        const bq = q as BuilderQuestion
        return (
          <div key={i} className="flex gap-2 rounded border border-border p-2">
            <Input
              placeholder="Name"
              value={bq.name}
              onChange={(e) => update(i, { name: e.target.value })}
              className="w-28 text-sm"
            />
            <Input
              placeholder="Title"
              value={bq.title}
              onChange={(e) => update(i, { title: e.target.value })}
              className="flex-1 text-sm"
            />
            <select
              className="rounded border border-border bg-background px-1 text-sm"
              value={bq.type}
              onChange={(e) => update(i, { type: e.target.value as FieldType })}
            >
              {(Object.keys(TYPE_LABELS) as FieldType[]).map((t) => (
                <option key={t} value={t}>
                  {TYPE_LABELS[t]}
                </option>
              ))}
            </select>
            <Button variant="ghost" size="sm" onClick={() => remove(i)}>
              ✕
            </Button>
          </div>
        )
      })}
      <Button type="button" variant="outline" size="sm" onClick={add}>
        + Add question
      </Button>
    </div>
  )
}
