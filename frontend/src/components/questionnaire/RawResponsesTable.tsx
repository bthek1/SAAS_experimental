import { ChevronDown, ChevronUp } from "lucide-react"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { formatDateTime } from "@/lib/date"
import type { Questionnaire } from "@/types/questionnaires"

const TRUNCATE_LENGTH = 120

export function RawResponsesTable({ responses }: { responses: Questionnaire[] }) {
  const [open, setOpen] = useState(false)
  const [expandedRows, setExpandedRows] = useState<ReadonlySet<string>>(new Set())

  function toggleRow(id: string) {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className="rounded-lg border">
      <button
        type="button"
        aria-expanded={open}
        className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium hover:bg-muted"
        onClick={() => setOpen((v) => !v)}
      >
        <span>Raw responses ({responses.length})</span>
        {open ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
      </button>

      {open && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>#</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Submitted</TableHead>
              <TableHead>Answers (JSON)</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {responses.map((r, index) => {
              const full = JSON.stringify(r.answers)
              const isLong = full.length > TRUNCATE_LENGTH
              const expanded = expandedRows.has(r.id)
              return (
                <TableRow key={r.id} className="align-top">
                  <TableCell className="text-muted-foreground">{index + 1}</TableCell>
                  <TableCell>{r.name || "—"}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {r.submittedAt ? formatDateTime(r.submittedAt) : "—"}
                  </TableCell>
                  <TableCell className="max-w-md font-mono text-xs whitespace-normal break-all">
                    {isLong && !expanded ? `${full.slice(0, TRUNCATE_LENGTH)}…` : full}
                    {isLong && (
                      <Button
                        size="xs"
                        variant="link"
                        className="ml-1"
                        onClick={() => toggleRow(r.id)}
                      >
                        {expanded ? "View less" : "View full"}
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
