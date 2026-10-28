// Pure conversion utilities between SurveyJS JSON and BuilderSurvey.
// No UI dependencies — safe to import anywhere.

export type FieldType =
  | "text"
  | "rating"
  | "radiogroup"
  | "checkbox"
  | "dropdown"
  | "comment"
  | "boolean"
  | "tagbox"
  | "imagepicker"
  | "multipletext"
  | "html"
  | "expression"
  | "matrix"
  | "matrixdropdown"
  | "matrixdynamic"
  | "panel"
  | "paneldynamic"

export const SUPPORTED_TYPES: FieldType[] = [
  "text",
  "rating",
  "radiogroup",
  "checkbox",
  "dropdown",
  "comment",
  "boolean",
  "tagbox",
  "imagepicker",
  "multipletext",
  "html",
  "expression",
  "matrix",
  "matrixdropdown",
  "matrixdynamic",
  "panel",
  "paneldynamic",
]

/** A single choice item — either a plain string or a {value, text} pair. */
export type ChoiceItem = string | { value: string; text: string }

/** A single sub-item for multipletext questions. */
export interface MultipleTextItem {
  name: string
  title?: string
  isRequired?: boolean
}

/** A single image-picker choice. */
export interface ImagePickerChoice {
  value: string
  text?: string
  imageLink?: string
}

/** A matrix row or column entry. */
export interface MatrixEntry {
  value: string
  text?: string
}

/** A column definition for matrixdropdown/matrixdynamic. */
export interface MatrixColumn {
  name: string
  title?: string
  cellType?: string
  choices?: ChoiceItem[]
}

export interface BuilderQuestion {
  name: string
  title: string
  type: FieldType
  required: boolean
  // radiogroup / checkbox / dropdown / tagbox
  choices?: ChoiceItem[]
  showOtherItem?: boolean
  showNoneItem?: boolean
  colCount?: number
  // rating
  rateMin?: number
  rateMax?: number
  rateStep?: number
  rateType?: string
  minRateDescription?: string
  maxRateDescription?: string
  // boolean
  labelTrue?: string
  labelFalse?: string
  // comment
  rows?: number
  // text
  inputType?: string
  placeholder?: string
  min?: string | number
  max?: string | number
  defaultValueExpression?: string
  step?: number
  validators?: Array<{ type: string }>
  // html
  html?: string
  // expression
  expression?: string
  displayStyle?: string
  suffix?: string
  prefix?: string
  // imagepicker
  imagePickerChoices?: ImagePickerChoice[]
  multiSelect?: boolean
  imageWidth?: number
  imageHeight?: number
  // multipletext
  items?: MultipleTextItem[]
  // matrix
  rows_?: MatrixEntry[]
  columns?: MatrixEntry[]
  // matrixdropdown / matrixdynamic
  matrixColumns?: MatrixColumn[]
  rowCount?: number
  addRowText?: string
  removeRowText?: string
  // conditional logic
  visibleIf?: string
  requiredIf?: string
  enableIf?: string
  // description
  description?: string
  // panel
  panelElements?: AnyQuestion[]
  panelState?: string
  // paneldynamic
  templateElements?: AnyQuestion[]
  panelCount?: number
  minPanelCount?: number
  maxPanelCount?: number
  panelAddText?: string
  panelRemoveText?: string
  templateTitle?: string
  /**
   * @deprecated No longer needed — the visual layer no longer rebuilds the JSON from
   * BuilderSurvey. Unknown properties are preserved because visual mode reads and patches
   * the raw surveyJson directly. This field will be removed in a future cleanup.
   */
  _rawExtra?: Record<string, unknown>
}

/**
 * @deprecated The visual layer no longer uses AdvancedQuestion — unknown element types are
 * rendered as read-only badges directly from the raw JSON. This type is kept only for
 * backwards-compatibility with existing tests.
 */
export interface AdvancedQuestion {
  _advanced: true
  name: string
  type: string
  raw: Record<string, unknown>
}

export type AnyQuestion = BuilderQuestion | AdvancedQuestion

export interface BuilderSurveySettings {
  description?: string
  locale?: string
  showProgressBar?: "off" | "top" | "bottom" | "both"
  showQuestionNumbers?: "on" | "off" | "onPage"
  checkErrorsMode?: "onNextPage" | "onValueChanged" | "onComplete"
  completedHtml?: string
}

export interface BuilderPage {
  name: string
  title?: string
  questions: AnyQuestion[]
}

/**
 * @deprecated BuilderSurvey is no longer part of the save pipeline. The visual editor
 * reads and patches the raw surveyJson object directly (PLAN-21). This type is kept only
 * for backwards-compatibility with existing tests that cover parseSurveyJson/buildSurveyJson.
 */
export interface BuilderSurvey {
  title: string
  pages: BuilderPage[]
  settings?: BuilderSurveySettings
  /**
   * @deprecated No longer needed — unknown top-level properties are preserved because the
   * visual layer never rebuilds the JSON from BuilderSurvey.
   */
  _rawMeta?: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Properties handled explicitly by the visual builder, keyed by question type.
 * Anything NOT in this set (plus the common set) is stored in _rawExtra and preserved verbatim. */
const COMMON_KNOWN_KEYS = new Set([
  "type",
  "name",
  "title",
  "isRequired",
  "description",
  "visibleIf",
  "requiredIf",
  "enableIf",
])
const TYPE_KNOWN_KEYS: Record<string, Set<string>> = {
  text: new Set([
    "inputType",
    "placeholder",
    "min",
    "max",
    "step",
    "validators",
    "defaultValueExpression",
  ]),
  rating: new Set([
    "rateMin",
    "rateMax",
    "rateStep",
    "rateType",
    "minRateDescription",
    "maxRateDescription",
  ]),
  radiogroup: new Set(["choices", "showOtherItem", "showNoneItem", "colCount"]),
  checkbox: new Set(["choices", "showOtherItem", "showNoneItem", "colCount"]),
  dropdown: new Set(["choices", "showOtherItem", "showNoneItem", "colCount"]),
  tagbox: new Set(["choices", "showOtherItem", "showNoneItem", "colCount"]),
  imagepicker: new Set(["choices", "multiSelect", "imageWidth", "imageHeight"]),
  multipletext: new Set(["items"]),
  boolean: new Set(["labelTrue", "labelFalse"]),
  comment: new Set(["rows", "placeholder"]),
  html: new Set(["html"]),
  expression: new Set(["expression", "displayStyle", "suffix", "prefix"]),
  matrix: new Set(["rows", "columns"]),
  matrixdropdown: new Set(["rows", "columns"]),
  matrixdynamic: new Set(["rows", "columns", "rowCount", "addRowText", "removeRowText"]),
  panel: new Set(["elements", "state"]),
  paneldynamic: new Set([
    "templateElements",
    "panelCount",
    "minPanelCount",
    "maxPanelCount",
    "panelAddText",
    "panelRemoveText",
    "templateTitle",
  ]),
}

function collectRawExtra(
  el: Record<string, unknown>,
  type: string,
): Record<string, unknown> | undefined {
  const known = new Set([...COMMON_KNOWN_KEYS, ...(TYPE_KNOWN_KEYS[type] ?? [])])
  const extra: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(el)) {
    if (!known.has(k)) extra[k] = v
  }
  return Object.keys(extra).length ? extra : undefined
}

/** True for plain JSON objects (not arrays, not null). */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

/** The value itself when it is a plain object, otherwise an empty object. */
function asRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {}
}

/** The value itself when it is an array, otherwise an empty array. */
function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function isSupported(type: string): type is FieldType {
  return (SUPPORTED_TYPES as string[]).includes(type)
}

/** Normalise a SurveyJS choices entry, preserving {value, text} pairs. */
function normaliseChoice(c: unknown): ChoiceItem {
  if (typeof c === "string") return c
  if (c && typeof c === "object") {
    const obj = c as Record<string, unknown>
    const value = String(obj.value ?? "")
    const text = String(obj.text ?? obj.value ?? "")
    // Keep as object only when value and text differ
    if (text !== value) return { value, text }
    return value
  }
  return String(c)
}

/** Serialise a ChoiceItem back to SurveyJS format. */
function serialiseChoice(c: ChoiceItem): unknown {
  if (typeof c === "string") return c
  if (c.value === c.text) return c.value
  return { value: c.value, text: c.text }
}

/** Normalise a {value, text?} entry (for matrix rows/columns). */
function normaliseEntry(c: unknown): MatrixEntry {
  if (typeof c === "string") return { value: c }
  if (c && typeof c === "object") {
    const obj = c as Record<string, unknown>
    return { value: String(obj.value ?? ""), text: obj.text ? String(obj.text) : undefined }
  }
  return { value: String(c) }
}

// ---------------------------------------------------------------------------
// parseRawElements (shared by parseSurveyJson and panel recursion)
// ---------------------------------------------------------------------------

function parseRawElements(rawElements: unknown[]): AnyQuestion[] {
  return rawElements.map((rawElement) => {
    const el = asRecord(rawElement)
    const type = typeof el.type === "string" ? el.type : "text"
    const name = typeof el.name === "string" ? el.name : ""

    if (!isSupported(type)) {
      return { _advanced: true, name, type, raw: el } satisfies AdvancedQuestion
    }

    const q: BuilderQuestion = {
      name,
      title: typeof el.title === "string" ? el.title : name,
      type: type as FieldType,
      required: el.isRequired === true,
    }

    if (el.description) q.description = String(el.description)
    if (el.visibleIf) q.visibleIf = String(el.visibleIf)
    if (el.requiredIf) q.requiredIf = String(el.requiredIf)
    if (el.enableIf) q.enableIf = String(el.enableIf)

    if (type === "radiogroup" || type === "checkbox" || type === "dropdown" || type === "tagbox") {
      q.choices = asArray(el.choices).map(normaliseChoice)
      if (el.showOtherItem) q.showOtherItem = true
      if (el.showNoneItem) q.showNoneItem = true
      if (typeof el.colCount === "number") q.colCount = el.colCount
    }

    if (type === "imagepicker") {
      q.imagePickerChoices = asArray(el.choices).map((c) => {
        if (typeof c === "string") return { value: c }
        const o = asRecord(c)
        return {
          value: String(o.value ?? ""),
          text: o.text ? String(o.text) : undefined,
          imageLink: o.imageLink ? String(o.imageLink) : undefined,
        }
      })
      if (typeof el.multiSelect === "boolean") q.multiSelect = el.multiSelect
      if (typeof el.imageWidth === "number") q.imageWidth = el.imageWidth
      if (typeof el.imageHeight === "number") q.imageHeight = el.imageHeight
    }

    if (type === "multipletext") {
      q.items = asArray(el.items).map((item) => {
        const o = asRecord(item)
        return {
          name: String(o.name ?? ""),
          title: o.title ? String(o.title) : undefined,
          isRequired: o.isRequired === true,
        }
      })
    }

    if (type === "rating") {
      q.rateMin = typeof el.rateMin === "number" ? el.rateMin : 1
      q.rateMax = typeof el.rateMax === "number" ? el.rateMax : 5
      if (el.rateStep !== undefined) q.rateStep = Number(el.rateStep)
      if (el.rateType) q.rateType = String(el.rateType)
      if (el.minRateDescription) q.minRateDescription = String(el.minRateDescription)
      if (el.maxRateDescription) q.maxRateDescription = String(el.maxRateDescription)
    }

    if (type === "boolean") {
      if (el.labelTrue) q.labelTrue = String(el.labelTrue)
      if (el.labelFalse) q.labelFalse = String(el.labelFalse)
    }

    if (type === "comment") {
      if (typeof el.rows === "number") q.rows = el.rows
      if (el.placeholder) q.placeholder = String(el.placeholder)
    }

    if (type === "text") {
      if (el.inputType) q.inputType = String(el.inputType)
      if (el.placeholder) q.placeholder = String(el.placeholder)
      if (el.min !== undefined) q.min = el.min as string | number
      if (el.max !== undefined) q.max = el.max as string | number
      if (typeof el.step === "number") q.step = el.step
      if (Array.isArray(el.validators)) q.validators = el.validators as Array<{ type: string }>
      if (el.defaultValueExpression) q.defaultValueExpression = String(el.defaultValueExpression)
    }

    if (type === "html") {
      if (el.html) q.html = String(el.html)
    }

    if (type === "expression") {
      if (el.expression) q.expression = String(el.expression)
      if (el.displayStyle) q.displayStyle = String(el.displayStyle)
      if (el.suffix) q.suffix = String(el.suffix)
      if (el.prefix) q.prefix = String(el.prefix)
    }

    if (type === "matrix") {
      q.rows_ = asArray(el.rows).map(normaliseEntry)
      q.columns = asArray(el.columns).map(normaliseEntry)
    }

    if (type === "matrixdropdown" || type === "matrixdynamic") {
      q.rows_ = asArray(el.rows).map(normaliseEntry)
      q.matrixColumns = asArray(el.columns).map((c) => {
        const o = asRecord(c)
        return {
          name: String(o.name ?? ""),
          title: o.title ? String(o.title) : undefined,
          cellType: o.cellType ? String(o.cellType) : undefined,
          choices: Array.isArray(o.choices) ? o.choices.map(normaliseChoice) : undefined,
        }
      })
      if (type === "matrixdynamic") {
        if (typeof el.rowCount === "number") q.rowCount = el.rowCount
        if (el.addRowText) q.addRowText = String(el.addRowText)
        if (el.removeRowText) q.removeRowText = String(el.removeRowText)
      }
    }

    if (type === "panel") {
      q.panelElements = parseRawElements(asArray(el.elements))
      if (el.state) q.panelState = String(el.state)
    }

    if (type === "paneldynamic") {
      q.templateElements = parseRawElements(asArray(el.templateElements))
      if (typeof el.panelCount === "number") q.panelCount = el.panelCount
      if (typeof el.minPanelCount === "number") q.minPanelCount = el.minPanelCount
      if (typeof el.maxPanelCount === "number") q.maxPanelCount = el.maxPanelCount
      if (el.panelAddText) q.panelAddText = String(el.panelAddText)
      if (el.panelRemoveText) q.panelRemoveText = String(el.panelRemoveText)
      if (el.templateTitle) q.templateTitle = String(el.templateTitle)
    }

    // Preserve any SurveyJS properties not explicitly managed above.
    const extra = collectRawExtra(el, type)
    if (extra) q._rawExtra = extra

    return q
  })
}

// ---------------------------------------------------------------------------
// parseSurveyJson
// ---------------------------------------------------------------------------

/**
 * Convert a raw SurveyJS JSON object → BuilderSurvey (best-effort).
 *
 * @deprecated No longer part of the save pipeline. The visual editor (PLAN-21) reads and
 * patches the raw surveyJson object directly; calling this function is unnecessary and
 * risks silently dropping unknown SurveyJS properties. Kept only for existing tests.
 */
export function parseSurveyJson(json: Record<string, unknown>): BuilderSurvey {
  const title = typeof json.title === "string" ? json.title : ""

  // Preserve all top-level keys the visual builder doesn't manage
  const KNOWN_TOP_LEVEL = new Set([
    "title",
    "pages",
    "elements",
    "description",
    "locale",
    "showProgressBar",
    "showQuestionNumbers",
    "checkErrorsMode",
    "completedHtml",
  ])
  const _rawMeta: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(json)) {
    if (!KNOWN_TOP_LEVEL.has(k)) _rawMeta[k] = v
  }

  // Extract survey-level settings
  const settings: BuilderSurveySettings = {}
  if (typeof json.description === "string") settings.description = json.description
  if (typeof json.locale === "string") settings.locale = json.locale
  if (json.showProgressBar)
    settings.showProgressBar = json.showProgressBar as BuilderSurveySettings["showProgressBar"]
  if (json.showQuestionNumbers)
    settings.showQuestionNumbers =
      json.showQuestionNumbers as BuilderSurveySettings["showQuestionNumbers"]
  if (json.checkErrorsMode)
    settings.checkErrorsMode = json.checkErrorsMode as BuilderSurveySettings["checkErrorsMode"]
  if (typeof json.completedHtml === "string") settings.completedHtml = json.completedHtml
  const hasSettings = Object.keys(settings).length > 0

  let builderPages: BuilderPage[]

  if (Array.isArray(json.pages) && json.pages.length > 0) {
    // Paged format: { pages: [{ name, title?, elements: [...] }] }
    builderPages = json.pages.map((rawPage: unknown, i) => {
      const p = asRecord(rawPage)
      return {
        name: typeof p.name === "string" ? p.name : `page${i + 1}`,
        title: typeof p.title === "string" ? p.title : undefined,
        questions: parseRawElements(asArray(p.elements)),
      }
    })
  } else if (Array.isArray(json.elements)) {
    // Flat format: { elements: [...] }
    builderPages = [{ name: "page1", questions: parseRawElements(json.elements) }]
  } else {
    builderPages = [{ name: "page1", questions: [] }]
  }

  return {
    title,
    pages: builderPages,
    settings: hasSettings ? settings : undefined,
    _rawMeta: Object.keys(_rawMeta).length ? _rawMeta : undefined,
  }
}

// ---------------------------------------------------------------------------
// buildElements (shared by buildSurveyJson and panel recursion)
// ---------------------------------------------------------------------------

function buildElements(questions: AnyQuestion[]): unknown[] {
  return questions.map((q) => {
    if ("_advanced" in q && q._advanced) {
      return q.raw
    }

    const bq = q as BuilderQuestion
    // Start with any extra properties not managed by the builder so they are preserved verbatim.
    // Explicitly managed fields set below will overwrite anything from _rawExtra with the same key.
    const el: Record<string, unknown> = { ...(bq._rawExtra ?? {}) }
    el.type = bq.type
    el.name = bq.name
    el.title = bq.title

    if (bq.required) el.isRequired = true
    if (bq.description) el.description = bq.description
    if (bq.visibleIf) el.visibleIf = bq.visibleIf
    if (bq.requiredIf) el.requiredIf = bq.requiredIf
    if (bq.enableIf) el.enableIf = bq.enableIf

    if (
      bq.type === "radiogroup" ||
      bq.type === "checkbox" ||
      bq.type === "dropdown" ||
      bq.type === "tagbox"
    ) {
      el.choices = (bq.choices ?? []).map(serialiseChoice)
      if (bq.showOtherItem) el.showOtherItem = true
      if (bq.showNoneItem) el.showNoneItem = true
      if (bq.colCount !== undefined) el.colCount = bq.colCount
    }

    if (bq.type === "imagepicker") {
      el.choices = (bq.imagePickerChoices ?? []).map((c) => {
        if (!c.text && !c.imageLink) return c.value
        const out: Record<string, unknown> = { value: c.value }
        if (c.text) out.text = c.text
        if (c.imageLink) out.imageLink = c.imageLink
        return out
      })
      if (bq.multiSelect) el.multiSelect = true
      if (bq.imageWidth) el.imageWidth = bq.imageWidth
      if (bq.imageHeight) el.imageHeight = bq.imageHeight
    }

    if (bq.type === "multipletext") {
      el.items = (bq.items ?? []).map((item) => {
        const out: Record<string, unknown> = { name: item.name }
        if (item.title) out.title = item.title
        if (item.isRequired) out.isRequired = true
        return out
      })
    }

    if (bq.type === "rating") {
      el.rateMin = bq.rateMin ?? 1
      el.rateMax = bq.rateMax ?? 5
      if (bq.rateStep !== undefined) el.rateStep = bq.rateStep
      if (bq.rateType) el.rateType = bq.rateType
      if (bq.minRateDescription) el.minRateDescription = bq.minRateDescription
      if (bq.maxRateDescription) el.maxRateDescription = bq.maxRateDescription
    }

    if (bq.type === "boolean") {
      if (bq.labelTrue) el.labelTrue = bq.labelTrue
      if (bq.labelFalse) el.labelFalse = bq.labelFalse
    }

    if (bq.type === "comment") {
      if (bq.rows) el.rows = bq.rows
      if (bq.placeholder) el.placeholder = bq.placeholder
    }

    if (bq.type === "text") {
      if (bq.inputType) el.inputType = bq.inputType
      if (bq.placeholder) el.placeholder = bq.placeholder
      if (bq.min !== undefined) el.min = bq.min
      if (bq.max !== undefined) el.max = bq.max
      if (bq.step !== undefined) el.step = bq.step
      if (bq.validators?.length) el.validators = bq.validators
      if (bq.defaultValueExpression) el.defaultValueExpression = bq.defaultValueExpression
    }

    if (bq.type === "html") {
      if (bq.html) el.html = bq.html
    }

    if (bq.type === "expression") {
      if (bq.expression) el.expression = bq.expression
      if (bq.displayStyle) el.displayStyle = bq.displayStyle
      if (bq.suffix) el.suffix = bq.suffix
      if (bq.prefix) el.prefix = bq.prefix
    }

    if (bq.type === "matrix") {
      el.rows = (bq.rows_ ?? []).map((r) => (r.text ? { value: r.value, text: r.text } : r.value))
      el.columns = (bq.columns ?? []).map((c) =>
        c.text ? { value: c.value, text: c.text } : c.value,
      )
    }

    if (bq.type === "matrixdropdown" || bq.type === "matrixdynamic") {
      el.rows = (bq.rows_ ?? []).map((r) => (r.text ? { value: r.value, text: r.text } : r.value))
      el.columns = (bq.matrixColumns ?? []).map((c) => {
        const out: Record<string, unknown> = { name: c.name }
        if (c.title) out.title = c.title
        if (c.cellType) out.cellType = c.cellType
        if (c.choices?.length) out.choices = c.choices.map(serialiseChoice)
        return out
      })
      if (bq.type === "matrixdynamic") {
        if (bq.rowCount !== undefined) el.rowCount = bq.rowCount
        if (bq.addRowText) el.addRowText = bq.addRowText
        if (bq.removeRowText) el.removeRowText = bq.removeRowText
      }
    }

    if (bq.type === "panel") {
      el.elements = buildElements(bq.panelElements ?? [])
      if (bq.panelState) el.state = bq.panelState
    }

    if (bq.type === "paneldynamic") {
      el.templateElements = buildElements(bq.templateElements ?? [])
      if (bq.panelCount !== undefined) el.panelCount = bq.panelCount
      if (bq.minPanelCount !== undefined) el.minPanelCount = bq.minPanelCount
      if (bq.maxPanelCount !== undefined) el.maxPanelCount = bq.maxPanelCount
      if (bq.panelAddText) el.panelAddText = bq.panelAddText
      if (bq.panelRemoveText) el.panelRemoveText = bq.panelRemoveText
      if (bq.templateTitle) el.templateTitle = bq.templateTitle
    }

    return el
  })
}

// ---------------------------------------------------------------------------
// buildSurveyJson
// ---------------------------------------------------------------------------

/**
 * Convert a BuilderSurvey → minimal valid SurveyJS JSON object.
 *
 * @deprecated No longer part of the save pipeline. The visual editor (PLAN-21) never
 * rebuilds the JSON from BuilderSurvey; every edit is a targeted patch on the raw
 * surveyJson object. Kept only for existing tests.
 */
export function buildSurveyJson(survey: BuilderSurvey): object {
  const outputPages = survey.pages.map((p) => {
    const page: Record<string, unknown> = { name: p.name, elements: buildElements(p.questions) }
    if (p.title) page.title = p.title
    return page
  })

  const result: Record<string, unknown> = {
    ...(survey._rawMeta ?? {}),
    pages: outputPages,
  }

  if (survey.title) result.title = survey.title

  // Emit settings fields (these override anything in _rawMeta with the same key)
  if (survey.settings) {
    const s = survey.settings
    if (s.description) result.description = s.description
    if (s.locale) result.locale = s.locale
    if (s.showProgressBar) result.showProgressBar = s.showProgressBar
    if (s.showQuestionNumbers) result.showQuestionNumbers = s.showQuestionNumbers
    if (s.checkErrorsMode) result.checkErrorsMode = s.checkErrorsMode
    if (s.completedHtml) result.completedHtml = s.completedHtml
  }

  return result
}

// ---------------------------------------------------------------------------
// generateUniqueName
// ---------------------------------------------------------------------------

/** Generate a unique question name (q1, q2, …) given existing names. */
export function generateUniqueName(existingNames: string[]): string {
  const nameSet = new Set(existingNames)
  let i = 1
  while (nameSet.has(`q${i}`)) i++
  return `q${i}`
}
