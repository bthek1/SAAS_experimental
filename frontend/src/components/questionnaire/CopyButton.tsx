import { Check, Copy } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"

interface CopyButtonProps {
  text: string
  label?: string
}

export function CopyButton({ text, label = "Copy link" }: CopyButtonProps) {
  const { copied, copy } = useCopyToClipboard()
  return (
    <Button size="sm" variant="outline" onClick={() => void copy(text)}>
      {copied ? <Check /> : <Copy />}
      {copied ? "Copied" : label}
    </Button>
  )
}
