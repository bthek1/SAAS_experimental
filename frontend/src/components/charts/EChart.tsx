import type { EChartsOption } from "echarts"
import ReactECharts from "echarts-for-react"

interface EChartProps {
  option: EChartsOption
  className?: string
  /** Re-evaluated only when `option` changes; pass `false` to keep prior state. */
  notMerge?: boolean
}

/**
 * Thin wrapper around `echarts-for-react`. Import this lazily
 * (`lazy(() => import("@/components/charts/EChart"))`) so the echarts bundle
 * stays out of the initial chunk.
 */
export default function EChart({
  option,
  className,
  notMerge = true,
}: EChartProps) {
  // Size comes from `className` on the outer div. An inline height on
  // ReactECharts itself would override any Tailwind height class.
  return (
    <div className={className}>
      <ReactECharts
        option={option}
        notMerge={notMerge}
        style={{ height: "100%", width: "100%" }}
      />
    </div>
  )
}
