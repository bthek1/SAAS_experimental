import { ArrowDown, ArrowUp, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { moveItem, removeAt } from "@/lib/list"
import type { QuestionnaireType } from "@/types/questionnaires"

interface OrderedTypePickerProps {
  value: string[]
  onChange: (ids: string[]) => void
  options: QuestionnaireType[]
  id?: string
}

/** Ordered multi-select of the user's questionnaire types (a battery's slots). */
export function OrderedTypePicker({ value, onChange, options, id }: OrderedTypePickerProps) {
  const titleOf = (typeId: string) => options.find((t) => t.id === typeId)?.title ?? typeId

  return (
    <div className="space-y-2">
      {value.length === 0 ? (
        <p className="text-sm text-muted-foreground">No questionnaire types added yet.</p>
      ) : (
        <ol className="space-y-1">
          {value.map((typeId, index) => (
            <li
              key={`${typeId}-${index}`}
              className="flex items-center gap-2 rounded-lg border bg-card px-3 py-1.5 text-sm"
            >
              <span className="w-5 text-muted-foreground">{index + 1}.</span>
              <span className="flex-1">{titleOf(typeId)}</span>
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                aria-label={`Move ${titleOf(typeId)} up`}
                disabled={index === 0}
                onClick={() => onChange(moveItem(value, index, -1))}
              >
                <ArrowUp />
              </Button>
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                aria-label={`Move ${titleOf(typeId)} down`}
                disabled={index === value.length - 1}
                onClick={() => onChange(moveItem(value, index, 1))}
              >
                <ArrowDown />
              </Button>
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                aria-label={`Remove ${titleOf(typeId)}`}
                onClick={() => onChange(removeAt(value, index))}
              >
                <X />
              </Button>
            </li>
          ))}
        </ol>
      )}
      <NativeSelect
        id={id}
        aria-label="Add a questionnaire type"
        className="w-full"
        value=""
        onChange={(e) => {
          if (e.target.value) onChange([...value, e.target.value])
        }}
      >
        <NativeSelectOption value="">Add a questionnaire type…</NativeSelectOption>
        {options.map((t) => (
          <NativeSelectOption key={t.id} value={t.id}>
            {t.title}
          </NativeSelectOption>
        ))}
      </NativeSelect>
    </div>
  )
}
