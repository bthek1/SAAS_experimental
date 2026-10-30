import { Link } from "@tanstack/react-router"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { formatRelative } from "@/lib/date"
import type { DashboardSummary } from "@/types/dashboard"

export function RecentSubmissions({ rows }: { rows: DashboardSummary["recentSubmissions"] }) {
  return (
    <Card className="gap-2" role="region" aria-label="Recent submissions">
      <CardHeader>
        <CardTitle>Recent submissions</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            No submissions in this period.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="text-right">Submitted</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-medium">
                    <Link
                      to="/questionnaires/$id/results"
                      params={{ id: r.id }}
                      className="hover:underline"
                    >
                      {r.name || "Untitled"}
                    </Link>
                  </TableCell>
                  <TableCell>{r.questionnaireTypeTitle}</TableCell>
                  <TableCell className="text-right text-muted-foreground">
                    {formatRelative(r.submittedAt)}
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
