import { ChevronLeft, ChevronRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { PAGE_SIZE } from "@/api/pagination"

interface PagerProps {
  page: number
  count: number
  onPageChange: (page: number) => void
  pageSize?: number
}

/** Prev/Next controls for a paginated list. Hidden when it all fits on one page. */
export function Pager({ page, count, onPageChange, pageSize = PAGE_SIZE }: PagerProps) {
  const pages = Math.max(1, Math.ceil(count / pageSize))
  if (pages <= 1) return null
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between gap-4">
      <p className="text-sm text-muted-foreground">
        Page {page} of {pages} · {count} total
      </p>
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft /> Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={page >= pages}
          onClick={() => onPageChange(page + 1)}
        >
          Next <ChevronRight />
        </Button>
      </div>
    </nav>
  )
}
