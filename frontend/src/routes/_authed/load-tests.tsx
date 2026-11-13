import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { z } from "zod"
import {
  CacheTab,
  CapacityTab,
  FastapiTab,
  FixesTab,
  GrowthTab,
  MethodTab,
  MongoTab,
  SplitTab,
} from "@/components/loadtest/LoadTestTabs"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

const TABS = [
  { value: "capacity", label: "Capacity", Panel: CapacityTab },
  { value: "cache", label: "Cache", Panel: CacheTab },
  { value: "growth", label: "Data growth", Panel: GrowthTab },
  { value: "fixes", label: "Dashboard fixes", Panel: FixesTab },
  { value: "split", label: "Service split", Panel: SplitTab },
  { value: "mongo", label: "Postgres vs MongoDB", Panel: MongoTab },
  { value: "fastapi", label: "Django vs FastAPI", Panel: FastapiTab },
  { value: "method", label: "Method & open questions", Panel: MethodTab },
] as const

const tabValues = ["capacity", "cache", "growth", "fixes", "split", "mongo", "fastapi", "method"] as const
type TabValue = (typeof tabValues)[number]

const searchSchema = z.object({
  tab: z.enum(tabValues).optional().catch(undefined),
})

const KPIS = [
  {
    label: "Capacity on the latest code, mixed traffic",
    value: "~430–581 req/s",
    hint: "Up from ~86 req/s at the start. Three runs before the split into two services and one after gave this range, so read any single knee as rough. The earlier runs also used different ramps.",
  },
  {
    label: "p95, 10 minutes at ~215 req/s",
    value: "8.9 ms",
    hint: "Was 19 ms before the cache and threads",
  },
  {
    label: "Failed requests",
    value: "1",
    hint: "In 8.4 M requests across the 35 runs behind this page, a connection reset whose cause wasn't found. Overload showed up as queueing, not errors",
  },
  {
    label: "Busiest container",
    value: "saas-instances",
    hint: "79 % CPU at ~581 req/s, against 24 % on saas-db. Before the split, this load was on saas-app",
  },
]

export const Route = createFileRoute("/_authed/load-tests")({
  validateSearch: searchSchema,
  component: LoadTestsPage,
})

function LoadTestsPage() {
  const { tab = "capacity" } = Route.useSearch()
  const navigate = useNavigate({ from: "/load-tests" })

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Load test results</h1>
        <p className="text-sm text-muted-foreground">
          How the API's capacity changed with each deploy and code change, measured with k6 on the
          same small containers from 2 to 4 November 2026.
        </p>
      </div>

      <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" aria-label="Key figures">
        {KPIS.map((kpi) => (
          <li key={kpi.label}>
            <Card className="h-full gap-2 py-4">
              <CardHeader className="px-4">
                <CardDescription>{kpi.label}</CardDescription>
                <CardTitle className="text-2xl tabular-nums">{kpi.value}</CardTitle>
              </CardHeader>
              <CardContent className="px-4 text-xs text-muted-foreground">{kpi.hint}</CardContent>
            </Card>
          </li>
        ))}
      </ul>

      <p className="rounded-lg border border-dashed p-4 text-sm">
        <strong>Corrected 4 November 2026.</strong> k6's p95 figures for these runs were calculated
        from the start of each run, not per minute, so they lag and stay raised after a stall.
        Latency charts now plot each minute's mean instead, and any remaining p95 from those runs is
        marked "since run start". Knees are as recorded, so they still use that older figure, and an
        early stall could have held a run over the limit.{" "}
        <Link to="/load-tests" search={{ tab: "method" }} className="text-primary hover:underline">
          How this was measured.
        </Link>
      </p>

      <Tabs
        value={tab}
        onValueChange={(value: TabValue) => navigate({ search: { tab: value } })}
        className="gap-6"
      >
        <div className="overflow-x-auto">
          <TabsList>
            {TABS.map(({ value, label }) => (
              <TabsTrigger key={value} value={value} className="px-3">
                {label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        {TABS.map(({ value, Panel }) => (
          <TabsContent key={value} value={value}>
            <Panel />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
