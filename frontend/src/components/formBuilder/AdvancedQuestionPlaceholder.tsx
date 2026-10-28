import { useState } from "react"
import { Button } from "@/components/ui/button"

interface AdvancedQuestionPlaceholderProps {
  name: string
  type: string
  raw: Record<string, unknown>
  onRawChange: (raw: Record<string, unknown>) => void
  onDelete: () => void
}

export function AdvancedQuestionPlaceholder({
  name,
  type,
  raw,
  onRawChange,
  onDelete,
}: AdvancedQuestionPlaceholderProps) {
  const [text, setText] = useState(() => JSON.stringify(raw, null, 2))
  const [parseError, setParseError] = useState<string | null>(null)

  function handleChange(value: string) {
    setText(value)
    try {
      const parsed = JSON.parse(value) as Record<string, unknown>
      setParseError(null)
      onRawChange(parsed)
    } catch {
      setParseError("Invalid JSON")
    }
  }

  return (
    <div
      data-testid="advanced-question-placeholder"
      className="flex flex-col gap-2 rounded-lg border border-dashed border-border bg-muted px-4 py-3 text-sm"
    >
      <div className="flex items-center justify-between">
        <div>
          <span className="font-medium">{name}</span>
          <span className="ml-2 text-muted-foreground">({type})</span>
        </div>
        <Button size="sm" variant="destructive" onClick={onDelete} aria-label={`Delete ${name}`}>
          Delete
        </Button>
      </div>
      <textarea
        className="w-full rounded border border-border bg-background px-2 py-1 font-mono text-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        rows={6}
        value={text}
        onChange={(e) => handleChange(e.target.value)}
        aria-label="Raw question JSON"
        spellCheck={false}
      />
      {parseError && <p className="text-xs text-destructive">{parseError}</p>}
    </div>
  )
}
