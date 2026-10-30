import type { EChartsOption } from "echarts"
import { lazy, Suspense } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const EChart = lazy(() => import("@/components/charts/EChart"))

interface ChartCardProps {
  title: string
  description?: string
  option: EChartsOption
  /** Pixel height of the plot; bar charts grow with their row count. */
  height?: number
  isEmpty?: boolean
  emptyText?: string
}

export function ChartCard({
  title,
  description,
  option,
  height = 240,
  isEmpty = false,
  emptyText = "Nothing to show for this period.",
}: ChartCardProps) {
  return (
    <Card className="gap-2" role="region" aria-label={title}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        {isEmpty ? (
          <p className="py-12 text-center text-sm text-muted-foreground">{emptyText}</p>
        ) : (
          <div style={{ height }}>
            <Suspense
              fallback={<div className="h-full animate-pulse rounded-md bg-muted" />}
            >
              <EChart option={option} className="h-full w-full" />
            </Suspense>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
