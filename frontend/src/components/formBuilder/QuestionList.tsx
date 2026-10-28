import { Fragment, type ReactNode } from "react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import type { AnyQuestion, BuilderQuestion, AdvancedQuestion } from "@/lib/formBuilder"

interface QuestionListProps {
  questions: AnyQuestion[]
  selectedIndex: number | null
  onSelect: (index: number) => void
  onAdd: () => void
  onAddAt: (index: number) => void
  onDelete: (index: number) => void
  onDuplicate: (index: number) => void
  onMoveUp: (index: number) => void
  onMoveDown: (index: number) => void
  /** Rendered inline below the selected question row */
  renderEditor?: (index: number) => ReactNode
}

function isAdvanced(q: AnyQuestion): q is AdvancedQuestion {
  return "_advanced" in q && q._advanced === true
}

export function QuestionList({
  questions,
  selectedIndex,
  onSelect,
  onAdd,
  onAddAt,
  onDelete,
  onDuplicate,
  onMoveUp,
  onMoveDown,
  renderEditor,
}: QuestionListProps) {
  return (
    <div className="flex flex-col gap-2">
      {questions.length === 0 && (
        <div
          data-testid="empty-state"
          className="rounded-lg border border-dashed border-border py-10 text-center text-sm text-muted-foreground"
        >
          Add your first question
        </div>
      )}

      {questions.map((q, i) => {
        const label = isAdvanced(q)
          ? `[Advanced] ${q.name}`
          : `${(q as BuilderQuestion).title || q.name}`

        return (
          <Fragment key={q.name + i}>
            <div
              data-testid={`question-item-${i}`}
              className={cn(
                "group flex cursor-pointer items-center justify-between rounded border px-3 py-2 text-sm transition-colors",
                i === selectedIndex
                  ? "border-2 border-primary bg-card"
                  : "border border-border hover:bg-muted",
              )}
              onClick={() => onSelect(i === selectedIndex ? -1 : i)}
            >
              <span className="truncate">{label}</span>

              <div
                className="flex shrink-0 gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100 data-[selected=true]:opacity-100"
                data-selected={i === selectedIndex}
                onClick={(e) => e.stopPropagation()}
              >
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onAddAt(i)}
                  aria-label="Insert above"
                  title="Insert above"
                >
                  ↑+
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onDuplicate(i)}
                  aria-label="Duplicate question"
                  title="Duplicate"
                >
                  ⊕
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onAddAt(i + 1)}
                  aria-label="Insert below"
                  title="Insert below"
                >
                  ↓+
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={i === 0}
                  onClick={() => onMoveUp(i)}
                  aria-label="Move up"
                >
                  ↑
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={i === questions.length - 1}
                  onClick={() => onMoveDown(i)}
                  aria-label="Move down"
                >
                  ↓
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onDelete(i)}
                  aria-label="Delete question"
                  className="text-destructive"
                >
                  ✕
                </Button>
              </div>
            </div>

            {i === selectedIndex && renderEditor && (
              <div className="ml-3 border-l-2 border-primary pl-3">{renderEditor(i)}</div>
            )}
          </Fragment>
        )
      })}

      <Button size="sm" variant="outline" onClick={onAdd} data-testid="add-question-btn">
        + Add question
      </Button>
    </div>
  )
}
