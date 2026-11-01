import { Button } from "@/components/ui/button"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import type { DashboardRange } from "@/types/dashboard"
import type { QuestionnaireType } from "@/types/questionnaires"

const RANGES: { value: DashboardRange; label: string }[] = [
  { value: 7, label: "7 days" },
  { value: 30, label: "30 days" },
  { value: 90, label: "90 days" },
  { value: "all", label: "All time" },
]

interface DashboardFiltersProps {
  range: DashboardRange
  type: string | undefined
  types: QuestionnaireType[]
  onRangeChange: (range: DashboardRange) => void
  onTypeChange: (type: string | undefined) => void
}

export function DashboardFilters({
  range,
  type,
  types,
  onRangeChange,
  onTypeChange,
}: DashboardFiltersProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div role="group" aria-label="Date range" className="flex gap-1 rounded-lg border p-1">
        {RANGES.map((r) => (
          <Button
            key={r.value}
            size="sm"
            variant={r.value === range ? "secondary" : "ghost"}
            aria-pressed={r.value === range}
            onClick={() => onRangeChange(r.value)}
          >
            {r.label}
          </Button>
        ))}
      </div>
      <NativeSelect
        aria-label="Questionnaire type"
        value={type ?? ""}
        onChange={(e) => onTypeChange(e.target.value || undefined)}
      >
        <NativeSelectOption value="">All questionnaire types</NativeSelectOption>
        {types.map((t) => (
          <NativeSelectOption key={t.id} value={t.id}>
            {t.title}
          </NativeSelectOption>
        ))}
      </NativeSelect>
    </div>
  )
}
