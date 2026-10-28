import { CopyButton } from "@/components/questionnaire/CopyButton"

/** A read-only share URL with a copy button. */
export function ShareLink({ url }: { url: string }) {
  return (
    <div className="flex items-center gap-2">
      <code className="min-w-0 flex-1 truncate rounded-md border bg-muted px-3 py-1.5 text-xs">
        {url}
      </code>
      <CopyButton text={url} />
    </div>
  )
}
