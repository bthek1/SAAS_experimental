import { patchSurveyJson, spliceJsonArray, getNestedValue } from '@/lib/surveyPatch'

// ---------------------------------------------------------------------------
// patchSurveyJson — unit tests
// ---------------------------------------------------------------------------

describe('patchSurveyJson', () => {
  it('patches a top-level string property', () => {
    const json = { title: 'Old', pages: [] }
    const result = patchSurveyJson(json, ['title'], 'New')
    expect(result).toEqual({ title: 'New', pages: [] })
  })

  it('preserves all sibling keys when patching one key', () => {
    const json = { title: 'T', description: 'D', locale: 'en', pages: [] }
    const result = patchSurveyJson(json, ['title'], 'Updated')
    expect(result).toMatchObject({ description: 'D', locale: 'en', pages: [] })
  })

  it('patches a nested object property', () => {
    const json = { pages: [{ name: 'p1', elements: [{ name: 'q1', title: 'Old', type: 'text' }] }] }
    const result = patchSurveyJson(json, ['pages', 0, 'elements', 0, 'title'], 'New title')
    expect((result as typeof json).pages[0].elements[0].title).toBe('New title')
  })

  it('preserves sibling keys on nested objects', () => {
    const json = {
      pages: [
        { name: 'p1', elements: [{ name: 'q1', title: 'T', type: 'text', isRequired: true }] },
      ],
    }
    const result = patchSurveyJson(
      json,
      ['pages', 0, 'elements', 0, 'title'],
      'Changed',
    ) as typeof json
    const el = result.pages[0].elements[0]
    expect(el.name).toBe('q1')
    expect(el.type).toBe('text')
    expect(el.isRequired).toBe(true)
  })

  it('patches an array element via numeric index', () => {
    const json = { items: ['a', 'b', 'c'] }
    const result = patchSurveyJson(json, ['items', 1], 'B') as { items: string[] }
    expect(result.items).toEqual(['a', 'B', 'c'])
  })

  it('does not mutate the original object', () => {
    const original = { title: 'Original', pages: [{ name: 'p1' }] }
    const frozen = JSON.parse(JSON.stringify(original))
    patchSurveyJson(original, ['title'], 'Changed')
    expect(original).toEqual(frozen)
  })

  it('returns the value itself when path is empty', () => {
    const json = { title: 'T' }
    const replacement = { title: 'R', pages: [] }
    const result = patchSurveyJson(json, [], replacement)
    expect(result).toBe(replacement)
  })

  it('creates intermediate objects for deep paths that do not exist', () => {
    const json: Record<string, unknown> = {}
    const result = patchSurveyJson(json, ['a', 'b', 'c'], 42) as Record<string, unknown>
    expect((result.a as Record<string, unknown>)['b']).toEqual({ c: 42 })
  })

  it('preserves top-level unknown SurveyJS properties (e.g. triggers, logo)', () => {
    const json = {
      title: 'T',
      pages: [],
      triggers: [{ type: 'complete' }],
      logo: 'logo.png',
      calculatedValues: [{ name: 'cv1' }],
    }
    const result = patchSurveyJson(json, ['title'], 'Updated') as typeof json
    expect(result.triggers).toEqual([{ type: 'complete' }])
    expect(result.logo).toBe('logo.png')
    expect(result.calculatedValues).toEqual([{ name: 'cv1' }])
  })

  it('handles patching a boolean value', () => {
    const json = { showProgressBar: false }
    const result = patchSurveyJson(json, ['showProgressBar'], true) as typeof json
    expect(result.showProgressBar).toBe(true)
  })

  it('handles patching a null value', () => {
    const json = { locale: 'en' }
    const result = patchSurveyJson(json, ['locale'], null) as Record<string, unknown>
    expect(result.locale).toBeNull()
  })

  it('patches deeply nested array element property', () => {
    const json = {
      pages: [
        { name: 'p1', elements: [] },
        { name: 'p2', elements: [{ name: 'q1', title: 'Old', type: 'text', isRequired: false }] },
      ],
    }
    const result = patchSurveyJson(
      json,
      ['pages', 1, 'elements', 0, 'isRequired'],
      true,
    ) as typeof json
    expect(result.pages[1].elements[0].isRequired).toBe(true)
    // sibling pages unaffected
    expect(result.pages[0].name).toBe('p1')
    expect(result.pages[0].elements).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// spliceJsonArray — unit tests
// ---------------------------------------------------------------------------

describe('spliceJsonArray', () => {
  it('inserts a new page at the end', () => {
    const json = { pages: [{ name: 'p1', elements: [] }] }
    const newPage = { name: 'p2', elements: [] }
    const result = spliceJsonArray(json, ['pages'], 1, 0, newPage)
    expect((result.pages as unknown[]).length).toBe(2)
    expect((result.pages as Array<{ name: string }>)[1].name).toBe('p2')
  })

  it('deletes an element from a page', () => {
    const json = {
      pages: [{ name: 'p1', elements: [{ name: 'q1' }, { name: 'q2' }, { name: 'q3' }] }],
    }
    const result = spliceJsonArray(json, ['pages', 0, 'elements'], 1, 1)
    const els = (result.pages as Array<{ elements: Array<{ name: string }> }>)[0].elements
    expect(els).toEqual([{ name: 'q1' }, { name: 'q3' }])
  })

  it('reorders elements (swap adjacent)', () => {
    const json = {
      pages: [{ name: 'p1', elements: [{ name: 'q1' }, { name: 'q2' }] }],
    }
    // Remove q1, insert after q2
    const els = json.pages[0].elements as Array<{ name: string }>
    const step1 = spliceJsonArray(json, ['pages', 0, 'elements'], 0, 1)
    const result = spliceJsonArray(step1, ['pages', 0, 'elements'], 1, 0, els[0])
    const finalEls = (result.pages as Array<{ elements: Array<{ name: string }> }>)[0].elements
    expect(finalEls[0].name).toBe('q2')
    expect(finalEls[1].name).toBe('q1')
  })

  it('does not mutate the original object', () => {
    const json = { pages: [{ name: 'p1', elements: [] }] }
    const frozen = JSON.parse(JSON.stringify(json))
    spliceJsonArray(json, ['pages'], 0, 1)
    expect(json).toEqual(frozen)
  })

  it('handles empty arrayPath target gracefully', () => {
    const json = { pages: [] as unknown[] }
    const result = spliceJsonArray(json, ['pages'], 0, 0, { name: 'new', elements: [] })
    expect((result.pages as unknown[]).length).toBe(1)
  })
})

// ---------------------------------------------------------------------------
// getNestedValue — unit tests
// ---------------------------------------------------------------------------

describe('getNestedValue', () => {
  it('reads a top-level value', () => {
    expect(getNestedValue({ title: 'T' }, ['title'])).toBe('T')
  })

  it('reads a nested value', () => {
    const json = { pages: [{ elements: [{ name: 'q1' }] }] }
    expect(getNestedValue(json, ['pages', 0, 'elements', 0, 'name'])).toBe('q1')
  })

  it('returns undefined for a missing path', () => {
    expect(getNestedValue({}, ['pages', 0, 'title'])).toBeUndefined()
  })

  it('returns undefined when an ancestor is null', () => {
    const json = { pages: null }
    expect(getNestedValue(json, ['pages', 0])).toBeUndefined()
  })
})
