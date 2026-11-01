import { Link } from "@tanstack/react-router"
import { CopyButton } from "@/components/questionnaire/CopyButton"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { takeUrl } from "@/lib/shareLinks"
import type { DashboardSummary } from "@/types/dashboard"

export function StalePending({ rows }: { rows: DashboardSummary["stalePending"] }) {
  return (
    <Card className="gap-2" role="region" aria-label="Awaiting response">
      <CardHeader>
        <CardTitle>Awaiting response</CardTitle>
        <CardDescription>Sent more than a week ago and still not submitted.</CardDescription>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            Nothing overdue. Nice.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Waiting</TableHead>
                <TableHead className="text-right">Share link</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-medium">
                    <Link to="/questionnaires/$id" params={{ id: r.id }} className="hover:underline">
                      {r.name || "Untitled"}
                    </Link>
                  </TableCell>
                  <TableCell>{r.questionnaireTypeTitle}</TableCell>
                  <TableCell className="text-muted-foreground">{r.ageDays} days</TableCell>
                  <TableCell className="text-right">
                    <CopyButton text={takeUrl(r.shareToken)} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
