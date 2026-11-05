import type { ReactNode } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { ResultColumn, ResultTableData } from "@/lib/loadtestResults"
import { cn } from "@/lib/utils"

function columnClass({ num, prose }: ResultColumn) {
  return cn(num && "text-right tabular-nums", prose && "min-w-64 whitespace-normal")
}

export function ResultsTable({ table }: { table: ResultTableData }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          {table.columns.map((col, i) => (
            <TableHead key={i} className={cn(columnClass(col), col.num && "whitespace-normal")}>
              {col.title}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {table.rows.map((row, r) => (
          <TableRow key={r}>
            {row.map((cell, c) => (
              <TableCell key={c} className={columnClass(table.columns[c])}>
                {table.columns[c].code ? <code className="text-xs">{cell}</code> : cell}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export function TableCard({
  title,
  description,
  table,
}: {
  title: string
  description?: string
  table: ResultTableData
}) {
  return (
    <Card className="gap-2" role="region" aria-label={title}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        <ResultsTable table={table} />
      </CardContent>
    </Card>
  )
}

export function Section({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  return (
    <section className="space-y-4">
      <h2 className="text-lg font-semibold">{title}</h2>
      {children}
    </section>
  )
}

/** Running text, kept to a readable line length on a wide page. */
export function Prose({ children }: { children: ReactNode }) {
  return <p className="max-w-3xl text-sm leading-relaxed">{children}</p>
}

export function Findings({ children }: { children: ReactNode }) {
  return (
    <ul className="max-w-3xl list-disc space-y-2 pl-5 text-sm leading-relaxed">{children}</ul>
  )
}
