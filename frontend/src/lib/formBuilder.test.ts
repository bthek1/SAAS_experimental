import { parseSurveyJson, buildSurveyJson, generateUniqueName } from "@/lib/formBuilder"
import type { BuilderSurvey, BuilderQuestion, AdvancedQuestion } from "@/lib/formBuilder"

// ---------------------------------------------------------------------------
// parseSurveyJson
// ---------------------------------------------------------------------------

describe("parseSurveyJson", () => {
  it("returns empty survey for minimal valid JSON", () => {
    const result = parseSurveyJson({ pages: [{ name: "page1", elements: [] }] })
    expect(result.title).toBe("")
    expect(result.pages[0].questions).toHaveLength(0)
  })

  it("parses survey title", () => {
    const result = parseSurveyJson({ title: "My Survey", pages: [] })
    expect(result.title).toBe("My Survey")
  })

  it("parses a text question", () => {
    const json = {
      pages: [
        {
          name: "page1",
          elements: [{ type: "text", name: "q1", title: "Your name", isRequired: true }],
        },
      ],
    }
    const result = parseSurveyJson(json)
    expect(result.pages[0].questions).toHaveLength(1)
    const q = result.pages[0].questions[0] as BuilderQuestion
    expect(q.type).toBe("text")
    expect(q.name).toBe("q1")
    expect(q.title).toBe("Your name")
    expect(q.required).toBe(true)
  })

  it("parses a radiogroup question with string choices", () => {
    const json = {
      pages: [
        {
          name: "page1",
          elements: [
            {
              type: "radiogroup",
              name: "q2",
              title: "Favourite colour",
              choices: ["Red", "Green", "Blue"],
            },
          ],
        },
      ],
    }
    const result = parseSurveyJson(json)
    const q = result.pages[0].questions[0] as BuilderQuestion
    expect(q.type).toBe("radiogroup")
    expect(q.choices).toEqual(["Red", "Green", "Blue"])
  })

  it("parses a radiogroup question with {value, text} object choices", () => {
    const json = {
      pages: [
        {
          name: "page1",
          elements: [
            {
              type: "radiogroup",
              name: "q3",
              choices: [
                { value: "r", text: "Red" },
                { value: "g", text: "Green" },
              ],
            },
          ],
        },
      ],
    }
    const result = parseSurveyJson(json)
    const q = result.pages[0].questions[0] as BuilderQuestion
    // {value, text} pairs are now preserved when value !== text
    expect(q.choices).toEqual([
      { value: "r", text: "Red" },
      { value: "g", text: "Green" },
    ])
  })

  it("parses a rating question with rateMin/rateMax", () => {
    const json = {
      pages: [
        {
          name: "page1",
          elements: [{ type: "rating", name: "q4", title: "Rate us", rateMin: 0, rateMax: 10 }],
        },
      ],
    }
    const result = parseSurveyJson(json)
    const q = result.pages[0].questions[0] as BuilderQuestion
    expect(q.type).toBe("rating")
    expect(q.rateMin).toBe(0)
    expect(q.rateMax).toBe(10)
  })

  it("uses default rateMin/rateMax when not provided", () => {
    const json = {
      pages: [{ name: "page1", elements: [{ type: "rating", name: "q5" }] }],
    }
    const result = parseSurveyJson(json)
    const q = result.pages[0].questions[0] as BuilderQuestion
    expect(q.rateMin).toBe(1)
    expect(q.rateMax).toBe(5)
  })

  it("marks unsupported types as advanced", () => {
    // Use a type that is NOT in SUPPORTED_TYPES (e.g. file, signaturepad)
    const raw = { type: "file", name: "f1" }
    const json = { pages: [{ name: "page1", elements: [raw] }] }
    const result = parseSurveyJson(json)
    const q = result.pages[0].questions[0] as AdvancedQuestion
    expect(q._advanced).toBe(true)
    expect(q.type).toBe("file")
    expect(q.raw).toEqual(raw)
  })

  it("collects elements across multiple pages", () => {
    const json = {
      pages: [
        { name: "p1", elements: [{ type: "text", name: "q1" }] },
        { name: "p2", elements: [{ type: "text", name: "q2" }] },
      ],
    }
    const result = parseSurveyJson(json)
    expect(result.pages).toHaveLength(2)
    expect(result.pages[0].questions).toHaveLength(1)
    expect(result.pages[1].questions).toHaveLength(1)
  })

  it("handles missing pages gracefully", () => {
    const result = parseSurveyJson({})
    expect(result.pages[0].questions).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// buildSurveyJson
// ---------------------------------------------------------------------------

describe("buildSurveyJson", () => {
  it("produces minimal valid JSON for empty survey", () => {
    const survey: BuilderSurvey = { title: "", pages: [{ name: "page1", questions: [] }] }
    const result = buildSurveyJson(survey) as Record<string, unknown>
    expect(result.pages).toBeDefined()
    const pages = result.pages as Array<{ name: string; elements: unknown[] }>
    expect(pages[0].name).toBe("page1")
    expect(pages[0].elements).toHaveLength(0)
  })

  it("includes survey title when non-empty", () => {
    const survey: BuilderSurvey = { title: "Hello", pages: [{ name: "page1", questions: [] }] }
    const result = buildSurveyJson(survey) as Record<string, unknown>
    expect(result.title).toBe("Hello")
  })

  it("omits title key when empty", () => {
    const survey: BuilderSurvey = { title: "", pages: [{ name: "page1", questions: [] }] }
    const result = buildSurveyJson(survey) as Record<string, unknown>
    expect(result.title).toBeUndefined()
  })

  it("serialises a text question correctly", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        { name: "page1", questions: [{ name: "q1", title: "Name", type: "text", required: true }] },
      ],
    }
    const result = buildSurveyJson(survey) as { pages: Array<{ elements: unknown[] }> }
    const el = result.pages[0].elements[0] as Record<string, unknown>
    expect(el.type).toBe("text")
    expect(el.name).toBe("q1")
    expect(el.title).toBe("Name")
    expect(el.isRequired).toBe(true)
  })

  it("omits isRequired when false", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [{ name: "q1", title: "Name", type: "text", required: false }],
        },
      ],
    }
    const result = buildSurveyJson(survey) as { pages: Array<{ elements: unknown[] }> }
    const el = result.pages[0].elements[0] as Record<string, unknown>
    expect(el.isRequired).toBeUndefined()
  })

  it("includes choices for radiogroup", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            { name: "q1", title: "Pick", type: "radiogroup", required: false, choices: ["A", "B"] },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as { pages: Array<{ elements: unknown[] }> }
    const el = result.pages[0].elements[0] as Record<string, unknown>
    expect(el.choices).toEqual(["A", "B"])
  })

  it("includes rateMin/rateMax for rating", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            { name: "q1", title: "Rate", type: "rating", required: false, rateMin: 0, rateMax: 10 },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as { pages: Array<{ elements: unknown[] }> }
    const el = result.pages[0].elements[0] as Record<string, unknown>
    expect(el.rateMin).toBe(0)
    expect(el.rateMax).toBe(10)
  })

  it("preserves advanced questions verbatim", () => {
    const raw = { type: "matrix", name: "mx1", rows: ["r1"], columns: ["c1"] }
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        { name: "page1", questions: [{ _advanced: true, name: "mx1", type: "matrix", raw }] },
      ],
    }
    const result = buildSurveyJson(survey) as { pages: Array<{ elements: unknown[] }> }
    expect(result.pages[0].elements[0]).toEqual(raw)
  })
})

// ---------------------------------------------------------------------------
// Round-trip
// ---------------------------------------------------------------------------

describe("round-trip parseSurveyJson → buildSurveyJson", () => {
  it("preserves all supported question types", () => {
    const original = {
      title: "Survey",
      pages: [
        {
          name: "page1",
          elements: [
            { type: "text", name: "q1", title: "Name", isRequired: true },
            { type: "rating", name: "q2", title: "Rate", rateMin: 1, rateMax: 5 },
            { type: "radiogroup", name: "q3", title: "Pick", choices: ["A", "B"] },
            { type: "checkbox", name: "q4", title: "Select", choices: ["X", "Y"] },
            { type: "dropdown", name: "q5", title: "Choose", choices: ["P", "Q"] },
            { type: "comment", name: "q6", title: "Notes" },
            { type: "boolean", name: "q7", title: "Agree" },
          ],
        },
      ],
    }

    const parsed = parseSurveyJson(original)
    const rebuilt = buildSurveyJson(parsed) as {
      title: string
      pages: Array<{ elements: Array<Record<string, unknown>> }>
    }

    expect(rebuilt.title).toBe("Survey")
    expect(rebuilt.pages[0].elements).toHaveLength(7)
    expect(rebuilt.pages[0].elements[0].type).toBe("text")
    expect(rebuilt.pages[0].elements[2].choices).toEqual(["A", "B"])
  })
})

// ---------------------------------------------------------------------------
// generateUniqueName
// ---------------------------------------------------------------------------

describe("generateUniqueName", () => {
  it("returns q1 when no existing names", () => {
    expect(generateUniqueName([])).toBe("q1")
  })

  it("skips names already in use", () => {
    expect(generateUniqueName(["q1", "q2"])).toBe("q3")
  })

  it("fills gaps", () => {
    expect(generateUniqueName(["q1", "q3"])).toBe("q2")
  })
})

// ---------------------------------------------------------------------------
// Phase 1: Rich choices (value/text pairs)
// ---------------------------------------------------------------------------

describe("parseSurveyJson — rich choices", () => {
  it("preserves {value, text} pairs when value !== text", () => {
    const json = {
      pages: [
        {
          name: "page1",
          elements: [
            {
              type: "radiogroup",
              name: "q1",
              choices: [
                { value: "r", text: "Red" },
                { value: "g", text: "Green" },
              ],
            },
          ],
        },
      ],
    }
    const result = parseSurveyJson(json)
    const q = result.pages[0].questions[0] as BuilderQuestion
    expect(q.choices).toEqual([
      { value: "r", text: "Red" },
      { value: "g", text: "Green" },
    ])
  })

  it("normalises {value, text} to plain string when value === text", () => {
    const json = {
      pages: [
        {
          name: "page1",
          elements: [
            { type: "checkbox", name: "q1", choices: [{ value: "Apple", text: "Apple" }] },
          ],
        },
      ],
    }
    const result = parseSurveyJson(json)
    const q = result.pages[0].questions[0] as BuilderQuestion
    expect(q.choices).toEqual(["Apple"])
  })

  it("parses showOtherItem and showNoneItem", () => {
    const json = {
      pages: [
        {
          name: "page1",
          elements: [
            {
              type: "radiogroup",
              name: "q1",
              choices: [],
              showOtherItem: true,
              showNoneItem: true,
            },
          ],
        },
      ],
    }
    const result = parseSurveyJson(json)
    const q = result.pages[0].questions[0] as BuilderQuestion
    expect(q.showOtherItem).toBe(true)
    expect(q.showNoneItem).toBe(true)
  })

  it("parses tagbox choices", () => {
    const json = {
      pages: [{ name: "page1", elements: [{ type: "tagbox", name: "q1", choices: ["A", "B"] }] }],
    }
    const result = parseSurveyJson(json)
    const q = result.pages[0].questions[0] as BuilderQuestion
    expect(q.type).toBe("tagbox")
    expect(q.choices).toEqual(["A", "B"])
  })
})

describe("buildSurveyJson — rich choices", () => {
  it("outputs plain string when choice value === text", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            {
              name: "q1",
              title: "Pick",
              type: "radiogroup",
              required: false,
              choices: [{ value: "Apple", text: "Apple" }],
            },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as {
      pages: Array<{ elements: Array<Record<string, unknown>> }>
    }
    expect(result.pages[0].elements[0].choices).toEqual(["Apple"])
  })

  it("outputs {value, text} object when value !== text", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            {
              name: "q1",
              title: "Pick",
              type: "radiogroup",
              required: false,
              choices: [{ value: "r", text: "Red" }],
            },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as {
      pages: Array<{ elements: Array<Record<string, unknown>> }>
    }
    expect(result.pages[0].elements[0].choices).toEqual([{ value: "r", text: "Red" }])
  })

  it("emits showOtherItem when set", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            {
              name: "q1",
              title: "Pick",
              type: "radiogroup",
              required: false,
              choices: [],
              showOtherItem: true,
            },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as {
      pages: Array<{ elements: Array<Record<string, unknown>> }>
    }
    expect(result.pages[0].elements[0].showOtherItem).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// Phase 2: Rich text question
// ---------------------------------------------------------------------------

describe("parseSurveyJson — text type", () => {
  it("parses inputType, placeholder, min, max, step, validators", () => {
    const json = {
      pages: [
        {
          name: "page1",
          elements: [
            {
              type: "text",
              name: "q1",
              inputType: "email",
              placeholder: "Enter email",
              validators: [{ type: "email" }],
            },
          ],
        },
      ],
    }
    const result = parseSurveyJson(json)
    const q = result.pages[0].questions[0] as BuilderQuestion
    expect(q.inputType).toBe("email")
    expect(q.placeholder).toBe("Enter email")
    expect(q.validators).toEqual([{ type: "email" }])
  })
})

describe("buildSurveyJson — text type", () => {
  it("round-trips inputType: email", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            {
              name: "q1",
              title: "Email",
              type: "text",
              required: false,
              inputType: "email",
              placeholder: "you@example.com",
              validators: [{ type: "email" }],
            },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as {
      pages: Array<{ elements: Array<Record<string, unknown>> }>
    }
    const el = result.pages[0].elements[0]
    expect(el.inputType).toBe("email")
    expect(el.placeholder).toBe("you@example.com")
    expect(el.validators).toEqual([{ type: "email" }])
  })
})

// ---------------------------------------------------------------------------
// Phase 3: boolean / comment / rating full config
// ---------------------------------------------------------------------------

describe("parseSurveyJson — boolean / comment / rating", () => {
  it("parses boolean labelTrue/labelFalse", () => {
    const json = {
      pages: [
        {
          name: "p1",
          elements: [{ type: "boolean", name: "q1", labelTrue: "Yes", labelFalse: "No" }],
        },
      ],
    }
    const q = parseSurveyJson(json).pages[0].questions[0] as BuilderQuestion
    expect(q.labelTrue).toBe("Yes")
    expect(q.labelFalse).toBe("No")
  })

  it("parses comment rows and placeholder", () => {
    const json = {
      pages: [
        {
          name: "p1",
          elements: [{ type: "comment", name: "q1", rows: 6, placeholder: "Type here" }],
        },
      ],
    }
    const q = parseSurveyJson(json).pages[0].questions[0] as BuilderQuestion
    expect(q.rows).toBe(6)
    expect(q.placeholder).toBe("Type here")
  })

  it("parses rating rateStep, rateType, min/max descriptions", () => {
    const json = {
      pages: [
        {
          name: "p1",
          elements: [
            {
              type: "rating",
              name: "q1",
              rateMin: 0,
              rateMax: 10,
              rateStep: 2,
              rateType: "stars",
              minRateDescription: "Poor",
              maxRateDescription: "Great",
            },
          ],
        },
      ],
    }
    const q = parseSurveyJson(json).pages[0].questions[0] as BuilderQuestion
    expect(q.rateStep).toBe(2)
    expect(q.rateType).toBe("stars")
    expect(q.minRateDescription).toBe("Poor")
    expect(q.maxRateDescription).toBe("Great")
  })
})

describe("buildSurveyJson — boolean / comment / rating", () => {
  it("round-trips boolean labels", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            {
              name: "q1",
              title: "Agree?",
              type: "boolean",
              required: false,
              labelTrue: "Yep",
              labelFalse: "Nope",
            },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as {
      pages: Array<{ elements: Array<Record<string, unknown>> }>
    }
    const el = result.pages[0].elements[0]
    expect(el.labelTrue).toBe("Yep")
    expect(el.labelFalse).toBe("Nope")
  })

  it("round-trips rating rateType and descriptions", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            {
              name: "q1",
              title: "Rate",
              type: "rating",
              required: false,
              rateMin: 1,
              rateMax: 5,
              rateType: "stars",
              minRateDescription: "Bad",
              maxRateDescription: "Good",
            },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as {
      pages: Array<{ elements: Array<Record<string, unknown>> }>
    }
    const el = result.pages[0].elements[0]
    expect(el.rateType).toBe("stars")
    expect(el.minRateDescription).toBe("Bad")
    expect(el.maxRateDescription).toBe("Good")
  })
})

// ---------------------------------------------------------------------------
// Phase 4: tagbox / imagepicker / multipletext
// ---------------------------------------------------------------------------

describe("parseSurveyJson — imagepicker / multipletext", () => {
  it("parses imagepicker choices", () => {
    const json = {
      pages: [
        {
          name: "p1",
          elements: [
            {
              type: "imagepicker",
              name: "q1",
              choices: [{ value: "dog", text: "Dog", imageLink: "https://dog.png" }],
              multiSelect: true,
              imageWidth: 200,
              imageHeight: 150,
            },
          ],
        },
      ],
    }
    const q = parseSurveyJson(json).pages[0].questions[0] as BuilderQuestion
    expect(q.type).toBe("imagepicker")
    expect(q.imagePickerChoices).toEqual([
      { value: "dog", text: "Dog", imageLink: "https://dog.png" },
    ])
    expect(q.multiSelect).toBe(true)
    expect(q.imageWidth).toBe(200)
    expect(q.imageHeight).toBe(150)
  })

  it("parses multipletext items", () => {
    const json = {
      pages: [
        {
          name: "p1",
          elements: [
            {
              type: "multipletext",
              name: "q1",
              items: [{ name: "first", title: "First name", isRequired: true }],
            },
          ],
        },
      ],
    }
    const q = parseSurveyJson(json).pages[0].questions[0] as BuilderQuestion
    expect(q.type).toBe("multipletext")
    expect(q.items).toEqual([{ name: "first", title: "First name", isRequired: true }])
  })
})

describe("buildSurveyJson — imagepicker / multipletext", () => {
  it("round-trips imagepicker", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            {
              name: "q1",
              title: "Pick",
              type: "imagepicker",
              required: false,
              imagePickerChoices: [{ value: "cat", imageLink: "https://cat.png" }],
            },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as {
      pages: Array<{ elements: Array<Record<string, unknown>> }>
    }
    const el = result.pages[0].elements[0]
    expect((el.choices as unknown[])[0]).toEqual({ value: "cat", imageLink: "https://cat.png" })
  })

  it("round-trips multipletext", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            {
              name: "q1",
              title: "Details",
              type: "multipletext",
              required: false,
              items: [{ name: "first", title: "First name" }],
            },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as {
      pages: Array<{ elements: Array<Record<string, unknown>> }>
    }
    const el = result.pages[0].elements[0]
    expect(el.items).toEqual([{ name: "first", title: "First name" }])
  })
})

// ---------------------------------------------------------------------------
// Phase 5: html / expression
// ---------------------------------------------------------------------------

describe("parseSurveyJson — html / expression", () => {
  it("parses html content", () => {
    const json = {
      pages: [{ name: "p1", elements: [{ type: "html", name: "h1", html: "<b>Hello</b>" }] }],
    }
    const q = parseSurveyJson(json).pages[0].questions[0] as BuilderQuestion
    expect(q.type).toBe("html")
    expect(q.html).toBe("<b>Hello</b>")
  })

  it("parses expression fields", () => {
    const json = {
      pages: [
        {
          name: "p1",
          elements: [
            {
              type: "expression",
              name: "e1",
              title: "Total",
              expression: "{q1} + {q2}",
              displayStyle: "currency",
              suffix: "USD",
            },
          ],
        },
      ],
    }
    const q = parseSurveyJson(json).pages[0].questions[0] as BuilderQuestion
    expect(q.type).toBe("expression")
    expect(q.expression).toBe("{q1} + {q2}")
    expect(q.displayStyle).toBe("currency")
    expect(q.suffix).toBe("USD")
  })
})

describe("buildSurveyJson — html / expression", () => {
  it("round-trips html", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            { name: "h1", title: "", type: "html", required: false, html: "<p>Info</p>" },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as {
      pages: Array<{ elements: Array<Record<string, unknown>> }>
    }
    expect(result.pages[0].elements[0].html).toBe("<p>Info</p>")
  })

  it("round-trips expression", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            {
              name: "e1",
              title: "Score",
              type: "expression",
              required: false,
              expression: "{q1} * 2",
              displayStyle: "decimal",
            },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as {
      pages: Array<{ elements: Array<Record<string, unknown>> }>
    }
    const el = result.pages[0].elements[0]
    expect(el.expression).toBe("{q1} * 2")
    expect(el.displayStyle).toBe("decimal")
  })
})

// ---------------------------------------------------------------------------
// Phase 6: Conditional logic
// ---------------------------------------------------------------------------

describe("parseSurveyJson — conditional logic", () => {
  it("parses visibleIf, requiredIf, enableIf", () => {
    const json = {
      pages: [
        {
          name: "p1",
          elements: [
            {
              type: "text",
              name: "q2",
              visibleIf: "{q1} = 'yes'",
              requiredIf: "{q1} = 'yes'",
              enableIf: "{q1} = 'yes'",
            },
          ],
        },
      ],
    }
    const q = parseSurveyJson(json).pages[0].questions[0] as BuilderQuestion
    expect(q.visibleIf).toBe("{q1} = 'yes'")
    expect(q.requiredIf).toBe("{q1} = 'yes'")
    expect(q.enableIf).toBe("{q1} = 'yes'")
  })
})

describe("buildSurveyJson — conditional logic", () => {
  it("emits visibleIf when set", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            {
              name: "q2",
              title: "Follow-up",
              type: "text",
              required: false,
              visibleIf: "{q1} = 'yes'",
            },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as {
      pages: Array<{ elements: Array<Record<string, unknown>> }>
    }
    expect(result.pages[0].elements[0].visibleIf).toBe("{q1} = 'yes'")
  })

  it("omits visibleIf when undefined", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        { name: "page1", questions: [{ name: "q1", title: "Q", type: "text", required: false }] },
      ],
    }
    const result = buildSurveyJson(survey) as {
      pages: Array<{ elements: Array<Record<string, unknown>> }>
    }
    expect(result.pages[0].elements[0].visibleIf).toBeUndefined()
  })
})

// ---------------------------------------------------------------------------
// Phase 7: Matrix types
// ---------------------------------------------------------------------------

describe("parseSurveyJson — matrix types", () => {
  it("parses matrix rows and columns", () => {
    const json = {
      pages: [
        {
          name: "p1",
          elements: [
            {
              type: "matrix",
              name: "m1",
              rows: ["Row1", { value: "r2", text: "Row 2" }],
              columns: ["Col1"],
            },
          ],
        },
      ],
    }
    const q = parseSurveyJson(json).pages[0].questions[0] as BuilderQuestion
    expect(q.type).toBe("matrix")
    expect(q.rows_).toEqual([{ value: "Row1" }, { value: "r2", text: "Row 2" }])
    expect(q.columns).toEqual([{ value: "Col1" }])
  })

  it("parses matrixdynamic with rowCount", () => {
    const json = {
      pages: [
        {
          name: "p1",
          elements: [
            {
              type: "matrixdynamic",
              name: "m1",
              rows: [],
              columns: [{ name: "col1", cellType: "text" }],
              rowCount: 3,
              addRowText: "Add",
              removeRowText: "Remove",
            },
          ],
        },
      ],
    }
    const q = parseSurveyJson(json).pages[0].questions[0] as BuilderQuestion
    expect(q.rowCount).toBe(3)
    expect(q.addRowText).toBe("Add")
    expect(q.matrixColumns?.[0].cellType).toBe("text")
  })
})

describe("buildSurveyJson — matrix types", () => {
  it("round-trips matrix", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            {
              name: "m1",
              title: "Matrix",
              type: "matrix",
              required: false,
              rows_: [{ value: "r1", text: "Row 1" }],
              columns: [{ value: "c1" }],
            },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as {
      pages: Array<{ elements: Array<Record<string, unknown>> }>
    }
    const el = result.pages[0].elements[0]
    expect(el.rows).toEqual([{ value: "r1", text: "Row 1" }])
    expect(el.columns).toEqual(["c1"])
  })

  it("round-trips matrixdynamic", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            {
              name: "m1",
              title: "Dynamic",
              type: "matrixdynamic",
              required: false,
              rows_: [],
              matrixColumns: [{ name: "col1", cellType: "dropdown", choices: ["A", "B"] }],
              rowCount: 2,
            },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as {
      pages: Array<{ elements: Array<Record<string, unknown>> }>
    }
    const el = result.pages[0].elements[0]
    expect(el.rowCount).toBe(2)
    expect((el.columns as Array<Record<string, unknown>>)[0].cellType).toBe("dropdown")
  })
})

// ---------------------------------------------------------------------------
// Phase 8: Panel types
// ---------------------------------------------------------------------------

describe("parseSurveyJson — panel types", () => {
  it("parses panel with nested elements", () => {
    const json = {
      pages: [
        {
          name: "p1",
          elements: [
            {
              type: "panel",
              name: "panel1",
              title: "Details",
              elements: [{ type: "text", name: "first", title: "First name" }],
              state: "collapsed",
            },
          ],
        },
      ],
    }
    const q = parseSurveyJson(json).pages[0].questions[0] as BuilderQuestion
    expect(q.type).toBe("panel")
    expect(q.panelElements).toHaveLength(1)
    expect((q.panelElements![0] as BuilderQuestion).name).toBe("first")
    expect(q.panelState).toBe("collapsed")
  })

  it("parses paneldynamic with templateElements", () => {
    const json = {
      pages: [
        {
          name: "p1",
          elements: [
            {
              type: "paneldynamic",
              name: "pd1",
              title: "Items",
              templateElements: [{ type: "text", name: "itemName" }],
              panelCount: 1,
              minPanelCount: 1,
              maxPanelCount: 5,
              panelAddText: "Add item",
              panelRemoveText: "Remove",
              templateTitle: "Item #{panelIndex}",
            },
          ],
        },
      ],
    }
    const q = parseSurveyJson(json).pages[0].questions[0] as BuilderQuestion
    expect(q.type).toBe("paneldynamic")
    expect(q.templateElements).toHaveLength(1)
    expect(q.panelCount).toBe(1)
    expect(q.maxPanelCount).toBe(5)
    expect(q.panelAddText).toBe("Add item")
    expect(q.templateTitle).toBe("Item #{panelIndex}")
  })
})

describe("buildSurveyJson — panel types", () => {
  it("round-trips panel with nested question", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            {
              name: "panel1",
              title: "Contact",
              type: "panel",
              required: false,
              panelElements: [{ name: "email", title: "Email", type: "text", required: true }],
              panelState: "expanded",
            },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as {
      pages: Array<{ elements: Array<Record<string, unknown>> }>
    }
    const el = result.pages[0].elements[0]
    expect(el.state).toBe("expanded")
    const nested = el.elements as Array<Record<string, unknown>>
    expect(nested[0].name).toBe("email")
    expect(nested[0].isRequired).toBe(true)
  })

  it("round-trips paneldynamic", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            {
              name: "pd1",
              title: "List",
              type: "paneldynamic",
              required: false,
              templateElements: [{ name: "item", title: "Item", type: "text", required: false }],
              panelCount: 2,
              panelAddText: "Add",
            },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as {
      pages: Array<{ elements: Array<Record<string, unknown>> }>
    }
    const el = result.pages[0].elements[0]
    expect(el.panelCount).toBe(2)
    expect(el.panelAddText).toBe("Add")
    expect((el.templateElements as unknown[]).length).toBe(1)
  })
})

// ---------------------------------------------------------------------------
// Phase 9: Multi-page support
// ---------------------------------------------------------------------------

describe("parseSurveyJson — multi-page", () => {
  it("maps each page to a BuilderPage with its questions", () => {
    const json = {
      pages: [
        { name: "p1", title: "Page 1", elements: [{ type: "text", name: "q1" }] },
        { name: "p2", elements: [{ type: "rating", name: "q2" }] },
      ],
    }
    const result = parseSurveyJson(json)
    expect(result.pages).toHaveLength(2)
    expect(result.pages[0].name).toBe("p1")
    expect(result.pages[0].title).toBe("Page 1")
    expect(result.pages[0].questions).toHaveLength(1)
    expect(result.pages[1].name).toBe("p2")
    expect(result.pages[1].questions).toHaveLength(1)
  })

  it("flat elements format produces a single page", () => {
    const json = { elements: [{ type: "text", name: "q1" }] }
    const result = parseSurveyJson(json)
    expect(result.pages).toHaveLength(1)
    expect(result.pages[0].name).toBe("page1")
  })
})

describe("buildSurveyJson — multi-page", () => {
  it("outputs one page per BuilderPage", () => {
    const survey: BuilderSurvey = {
      title: "Survey",
      pages: [
        {
          name: "p1",
          title: "Introduction",
          questions: [{ name: "q1", title: "Name", type: "text", required: false }],
        },
        {
          name: "p2",
          questions: [{ name: "q2", title: "Rating", type: "rating", required: false }],
        },
      ],
    }
    const result = buildSurveyJson(survey) as {
      pages: Array<{ name: string; title?: string; elements: unknown[] }>
    }
    expect(result.pages).toHaveLength(2)
    expect(result.pages[0].name).toBe("p1")
    expect(result.pages[0].title).toBe("Introduction")
    expect(result.pages[0].elements).toHaveLength(1)
    expect(result.pages[1].name).toBe("p2")
    expect(result.pages[1].title).toBeUndefined()
  })
})

// ---------------------------------------------------------------------------
// Phase 10: Survey-level settings
// ---------------------------------------------------------------------------

describe("parseSurveyJson — survey settings", () => {
  it("extracts showProgressBar", () => {
    const json = { showProgressBar: "top", pages: [] }
    const result = parseSurveyJson(json)
    expect(result.settings?.showProgressBar).toBe("top")
  })

  it("extracts description and locale", () => {
    const json = { description: "A survey", locale: "de", pages: [] }
    const result = parseSurveyJson(json)
    expect(result.settings?.description).toBe("A survey")
    expect(result.settings?.locale).toBe("de")
  })

  it("leaves settings undefined when absent", () => {
    const json = { pages: [] }
    const result = parseSurveyJson(json)
    expect(result.settings).toBeUndefined()
  })

  it("does not put settings fields in _rawMeta", () => {
    const json = { showProgressBar: "top", completedHtml: "<p>Done</p>", pages: [] }
    const result = parseSurveyJson(json)
    expect(result._rawMeta?.showProgressBar).toBeUndefined()
    expect(result._rawMeta?.completedHtml).toBeUndefined()
  })
})

describe("buildSurveyJson — survey settings", () => {
  it("emits showProgressBar when set", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [{ name: "page1", questions: [] }],
      settings: { showProgressBar: "bottom" },
    }
    const result = buildSurveyJson(survey) as Record<string, unknown>
    expect(result.showProgressBar).toBe("bottom")
  })

  it("does not emit settings when undefined", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [{ name: "page1", questions: [] }],
    }
    const result = buildSurveyJson(survey) as Record<string, unknown>
    expect(result.showProgressBar).toBeUndefined()
    expect(result.description).toBeUndefined()
  })
})

// ---------------------------------------------------------------------------
// Phase 19: colCount for radiogroup / checkbox
// ---------------------------------------------------------------------------

describe("parseSurveyJson — colCount", () => {
  it("reads colCount from radiogroup element", () => {
    const json = { elements: [{ type: "radiogroup", name: "q1", colCount: -1, choices: [] }] }
    const survey = parseSurveyJson(json)
    const q = survey.pages[0].questions[0] as BuilderQuestion
    expect(q.colCount).toBe(-1)
  })

  it("reads colCount from checkbox element", () => {
    const json = { elements: [{ type: "checkbox", name: "q1", colCount: 2, choices: [] }] }
    const survey = parseSurveyJson(json)
    const q = survey.pages[0].questions[0] as BuilderQuestion
    expect(q.colCount).toBe(2)
  })

  it("leaves colCount undefined when absent", () => {
    const json = { elements: [{ type: "radiogroup", name: "q1", choices: [] }] }
    const survey = parseSurveyJson(json)
    const q = survey.pages[0].questions[0] as BuilderQuestion
    expect(q.colCount).toBeUndefined()
  })
})

describe("buildSurveyJson — colCount", () => {
  it("emits colCount: -1 for radiogroup", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            {
              name: "q1",
              title: "Q1",
              type: "radiogroup",
              required: false,
              choices: [],
              colCount: -1,
            },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as Record<string, unknown>
    const pages = result.pages as Array<Record<string, unknown>>
    const elements = pages[0].elements as Array<Record<string, unknown>>
    expect(elements[0].colCount).toBe(-1)
  })

  it("emits colCount: 2 for checkbox", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            {
              name: "q1",
              title: "Q1",
              type: "checkbox",
              required: false,
              choices: [],
              colCount: 2,
            },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as Record<string, unknown>
    const pages = result.pages as Array<Record<string, unknown>>
    const elements = pages[0].elements as Array<Record<string, unknown>>
    expect(elements[0].colCount).toBe(2)
  })

  it("does not emit colCount when undefined", () => {
    const survey: BuilderSurvey = {
      title: "",
      pages: [
        {
          name: "page1",
          questions: [
            { name: "q1", title: "Q1", type: "radiogroup", required: false, choices: [] },
          ],
        },
      ],
    }
    const result = buildSurveyJson(survey) as Record<string, unknown>
    const pages = result.pages as Array<Record<string, unknown>>
    const elements = pages[0].elements as Array<Record<string, unknown>>
    expect(elements[0].colCount).toBeUndefined()
  })

  it("round-trips colCount through parse → build", () => {
    const json = {
      elements: [{ type: "radiogroup", name: "q1", colCount: -1, choices: ["A", "B"] }],
    }
    const survey = parseSurveyJson(json)
    const output = buildSurveyJson(survey) as Record<string, unknown>
    const pages = output.pages as Array<Record<string, unknown>>
    const elements = pages[0].elements as Array<Record<string, unknown>>
    expect(elements[0].colCount).toBe(-1)
  })
})
