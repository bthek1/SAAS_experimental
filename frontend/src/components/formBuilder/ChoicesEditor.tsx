import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import type { ChoiceItem } from "@/lib/formBuilder"
import { useState } from "react"

interface ChoicesEditorProps {
  choices: ChoiceItem[]
  onChange: (choices: ChoiceItem[]) => void
}

function isRichChoice(c: ChoiceItem): c is { value: string; text: string } {
  return typeof c === "object"
}

function allPlain(choices: ChoiceItem[]): boolean {
  return choices.every((c) => typeof c === "string")
}

export function ChoicesEditor({ choices, onChange }: ChoicesEditorProps) {
  // Start in rich mode if any choice is a {value, text} pair
  const [richMode, setRichMode] = useState(() => !allPlain(choices))

  function toggleMode() {
    if (richMode) {
      // rich → plain: flatten to plain strings (use `text` as the value if they differ)
      onChange(choices.map((c) => (isRichChoice(c) ? c.text || c.value : c)))
    } else {
      // plain → rich: convert plain strings to {value, text} pairs
      onChange(choices.map((c) => (typeof c === "string" ? { value: c, text: c } : c)))
    }
    setRichMode((prev) => !prev)
  }

  if (!richMode) {
    // ---- Simple / plain-text mode ----
    return (
      <div className="space-y-2">
        <Textarea
          value={choices.map((c) => (typeof c === "string" ? c : c.text || c.value)).join("\n")}
          onChange={(e) =>
            onChange(
              e.target.value
                .split("\n")
                .map((s) => s.trimEnd())
                .filter(Boolean),
            )
          }
          rows={4}
          placeholder="Option A&#10;Option B&#10;Option C"
          data-testid="choices-textarea"
        />
        <button
          type="button"
          onClick={toggleMode}
          className="text-xs text-primary hover:underline"
          data-testid="toggle-rich-choices"
        >
          Switch to value / label pairs
        </button>
      </div>
    )
  }

  // ---- Rich / table mode ----
  function updateRow(index: number, field: "value" | "text", val: string) {
    const updated = choices.map((c, i) => {
      if (i !== index) return c
      const pair = isRichChoice(c) ? c : { value: c, text: c }
      return { ...pair, [field]: val }
    })
    onChange(updated)
  }

  function addRow() {
    onChange([...choices, { value: "", text: "" }])
  }

  function removeRow(index: number) {
    onChange(choices.filter((_, i) => i !== index))
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[1fr_1fr_auto] gap-x-2 gap-y-1 text-xs font-medium text-muted-foreground">
        <span>Value</span>
        <span>Label</span>
        <span />
      </div>
      {choices.map((c, i) => {
        const value = isRichChoice(c) ? c.value : c
        const text = isRichChoice(c) ? c.text : c
        return (
          <div key={i} className="grid grid-cols-[1fr_1fr_auto] gap-x-2 gap-y-1">
            <Input
              value={value}
              onChange={(e) => updateRow(i, "value", e.target.value)}
              placeholder="value"
              data-testid={`choice-value-${i}`}
            />
            <Input
              value={text}
              onChange={(e) => updateRow(i, "text", e.target.value)}
              placeholder="label"
              data-testid={`choice-text-${i}`}
            />
            <Button
              variant="ghost"
              size="sm"
              onClick={() => removeRow(i)}
              data-testid={`choice-remove-${i}`}
            >
              ✕
            </Button>
          </div>
        )
      })}
      <div className="flex items-center gap-3">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={addRow}
          data-testid="choices-add-row"
        >
          + Add choice
        </Button>
        <button
          type="button"
          onClick={toggleMode}
          className="text-xs text-primary hover:underline"
          data-testid="toggle-plain-choices"
        >
          Switch to plain text
        </button>
      </div>
    </div>
  )
}
