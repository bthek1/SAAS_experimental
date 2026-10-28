import type { MetricResult } from "@/lib/metrics"

export function MetricCards({ metrics }: { metrics: MetricResult[] }) {
  if (metrics.length === 0) return null
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {metrics.map((m) => (
        <div key={m.name} className="rounded-lg border bg-card px-5 py-4">
          <p className="text-sm text-muted-foreground">{m.label}</p>
          <p className="text-3xl font-semibold text-primary">
            {m.value === null || m.value === undefined ? "—" : String(m.value)}
          </p>
        </div>
      ))}
    </div>
  )
}
