import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"

interface SurveyTitleEditorProps {
  value: string
  onChange: (value: string) => void
}

export function SurveyTitleEditor({ value, onChange }: SurveyTitleEditorProps) {
  return (
    <div className="space-y-1">
      <Label htmlFor="survey-title">Survey title</Label>
      <Input
        id="survey-title"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Enter survey title"
        data-testid="survey-title-input"
      />
    </div>
  )
}
