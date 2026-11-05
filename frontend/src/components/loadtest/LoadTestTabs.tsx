import { Link } from "@tanstack/react-router"
import { ChartCard } from "@/components/dashboard/ChartCard"
import { Findings, Prose, ResultsTable, Section, TableCard } from "@/components/loadtest/parts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useSeriesPalette } from "@/hooks/useChartPalette"
import {
  cacheKneesOption,
  cacheMixedOption,
  cacheReadOption,
  changesOption,
  changesTable,
  fixesOption,
  holdOption,
  nearPeakOption,
  rampOption,
  rampTable,
  soakCpuOption,
  soakLatencyOption,
} from "@/lib/loadtestCharts"
import {
  CHANGES,
  failureTable,
  holdTable,
  matchingTable,
  profileTable,
  readsTable,
  splitDeployTable,
  splitHoldTable,
  splitStressTable,
  trueP95Table,
} from "@/lib/loadtestResults"

const linkClass = "text-primary hover:underline"

export function CapacityTab() {
  const palette = useSeriesPalette()
  return (
    <div className="space-y-8">
      <Section title="Capacity after each change">
        <Prose>
          Capacity here is the <strong>knee</strong>: the highest rate in a stress run with no
          dropped iterations and the slowest endpoint group's p95, since run start, under about 150
          ms. Each row keeps the changes above it.
        </Prose>
        <ChartCard
          title="Knee per stress run, req/s"
          description="Mixed traffic (47 % of requests write). Every run starts from the same reset data."
          option={changesOption(palette)}
          height={Math.max(320, 48 + CHANGES.length * 48)}
        />
        <Prose>
          <strong>Read the gaps with care.</strong> The grey run repeated the settings above it and
          came out ~89 req/s higher, for a reason that was never found. A gain smaller than that
          isn't proven by the knee alone. The two big gains also show at matching rates: at ~125
          req/s pagination cut mean latency from 12 to 4.5 ms, and the cache cut Postgres rows read
          7 to 14 times. The later dashboard fixes used a shorter ramp, so they are{" "}
          <Link to="/load-tests" search={{ tab: "fixes" }} className={linkClass}>
            compared separately
          </Link>
          .
        </Prose>
        <TableCard title="The numbers at each knee" table={changesTable} />
      </Section>

      <Section title="Latency as the rate climbs">
        <Prose>
          Each line is one run, stepping up the rate until it reaches its knee (the dot). Further
          right and lower is better. Persistent connections and pagination flatten the curve.
          Threads leave it where it was. Mean latency passes 10 ms at about 250 req/s with
          pagination alone, and at about 430 req/s with the cache.
        </Prose>
        <ChartCard
          title="Mean latency in ms, all requests, by request rate"
          option={rampOption(palette)}
          height={380}
        />
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground">Show the table</summary>
          <div className="mt-2">
            <ResultsTable table={rampTable} />
          </div>
        </details>
      </Section>
    </div>
  )
}

export function CacheTab() {
  const palette = useSeriesPalette()
  return (
    <div className="space-y-8">
      <Section title="What the Redis cache did">
        <Prose>
          Back-to-back pairs on the final code, cache off then on, with dashboards, type lists and
          PDFs cached. The deploy holds <strong>about 28 % more traffic</strong> under both traffic
          mixes. Compare within these pairs only: they start at a higher rate, so they add fewer
          rows than the longer ramps on the Capacity tab.
        </Prose>
        <ChartCard
          title="Knee, cache off against on, req/s"
          option={cacheKneesOption(palette)}
          height={240}
        />
        <div className="grid gap-6 lg:grid-cols-2">
          <ChartCard
            title="Mixed traffic: mean latency, ms"
            option={cacheMixedOption(palette)}
            height={300}
          />
          <ChartCard
            title="Read-mostly traffic: mean latency, ms"
            description="Off the scale and not drawn: a one-minute stall in the cache-off run at 269 req/s (mean 536 ms)."
            option={cacheReadOption(palette)}
            height={300}
          />
        </div>
        <TableCard
          title="At matching rates"
          description="k6 p95 per endpoint in ms, since run start, so an earlier stall inflates the read-off column. Only the first three endpoints are cached: the others speed up because Postgres is less busy."
          table={matchingTable}
        />
        <Findings>
          <li>
            <strong>Most of the gain is less Postgres contention.</strong> The dashboards caused
            most of the rows read, and Postgres now reads 7 to 14 times fewer rows at matching
            rates.
          </li>
          <li>
            <strong>Almost all of it comes from the dashboards.</strong> The type-list and PDF
            caches passed their gates by small margins. A PDF hit is ~35 times faster (2.9 ms
            against 101 ms), but p95 barely moves (113 to 105 ms), and k6 redownloads far more often
            than real users are likely to.
          </li>
          <li>
            <strong>The read-mostly knee with the cache may be higher.</strong> That run ended on a
            stall while mean latency was about 10 ms.
          </li>
        </Findings>
      </Section>

      <Section title="When Redis fails">
        <Prose>
          Both tests ran at ~110 req/s of read-mostly traffic. The cache fails open: no request
          failed in either.
        </Prose>
        <TableCard title="Redis stopped and frozen" table={failureTable} />
      </Section>
    </div>
  )
}

export function GrowthTab() {
  const palette = useSeriesPalette()
  return (
    <div className="space-y-8">
      <Section title="What happens as data grows">
        <Prose>
          A soak at a constant ~350 req/s with the cache on. The respondent flow adds about 8,000
          questionnaires a minute. The first run{" "}
          <strong>fell off a cliff at about 236,000 rows</strong> (~12,000 per owner): saas-app ran
          out of CPU, k6 dropped 7,074 iterations after startup, and it was stopped at minute 35.
          After the dashboard fixes, the same command held the rate to minute 44,{" "}
          <strong>about 355,000 rows, with nothing dropped after startup</strong>. No request failed
          in either run.
        </Prose>
        <div className="grid gap-6 lg:grid-cols-2">
          <ChartCard
            title="Mean latency, ms, by minute"
            option={soakLatencyOption(palette)}
            height={300}
          />
          <ChartCard
            title="saas-app CPU, %, by minute"
            option={soakCpuOption(palette)}
            height={300}
          />
        </div>
        <Findings>
          <li>
            <strong>The new limit wasn't found.</strong> The later run was stopped at minute 45 to
            save time. CPU and Django p95 began rising at minute 42, and mean latency went from
            about 11 ms to 21–39 ms, so another limit may be close.
          </li>
          <li>
            <strong>Drift is much smaller.</strong> By minute 28 (about 228,000 rows) the mean was
            33 ms before the fixes and 7.5 ms after. It is reduced, not gone.
          </li>
          <li>
            <strong>This is one run each, at one rate.</strong> All rows are dated today, the worst
            case for the <code>days</code> windows. Read it as data per owner, not as time.
          </li>
        </Findings>
      </Section>

      <Section title="Holding a steady rate">
        <Prose>
          The same 10-minute hold, before and after. Runs add rows, so latency drifts upward during
          a hold. The cache cuts that drift but doesn't remove it, because a miss still pays for the
          full query. The earlier run also used sync workers, so this isn't a pure cache comparison.
        </Prose>
        <ChartCard
          title="Mean latency, ms, by minute, at ~215 req/s"
          option={holdOption(palette)}
          height={280}
        />
        <TableCard title="The two holds" table={holdTable} />
      </Section>
    </div>
  )
}

export function FixesTab() {
  const palette = useSeriesPalette()
  return (
    <Section title="What the dashboard fixes did">
      <Prose>
        Four changes, deployed together, so k6 can't separate them: a 500-row limit on the points in{" "}
        <code>dashboard/scores/</code>, the median found in the database, the owner on the battery
        join, and two partial indexes. The biggest effect is on rows per owner.{" "}
        <strong>Peak capacity isn't shown to have moved.</strong> The same stress test on the same
        code reached ~430, ~497 and ~573 req/s, against ~480 before, so run-to-run variation is
        bigger than any gain it could show. Mean latency is usually lower at matching rates, most
        clearly at the top: 32 ms before at ~480 req/s, against 16 and 7 ms after.
      </Prose>
      <ChartCard
        title="Stress: mean latency, ms, by request rate"
        option={fixesOption(palette)}
        height={340}
      />
      <TableCard
        title="True per-minute p95, stress run 3"
        description="The first run with histograms, so there is no earlier figure to compare with. Slowest endpoint group in each minute."
        table={trueP95Table}
      />
      <ChartCard
        title="15 minutes near peak rate: mean latency, ms, by minute"
        description="~445 req/s, about 10,000 new questionnaires a minute, reaching about 150,000 rows. Both from reset data, same code and command. Neither reached the stop rule and no request failed. Run 1 dropped 2,280 iterations in minutes 6 to 9 (saas-app at 82–90 % CPU), then recovered at about 78 %. Run 2 held about 60 % CPU and dropped none after startup."
        option={nearPeakOption(palette)}
        height={300}
      />
      <TableCard
        title="One owner's reads on the deploy, at the end of each soak"
        description="Median of 3 for the later run, with no other traffic. That owner has 18,416 questionnaires; the earlier one had 15,346."
        table={readsTable}
      />
      <TableCard
        title="Profile of a cache miss"
        description="A throwaway Postgres on the dev host, so read these as ratios. 300,000 questionnaires, the owner has 15,000, cache off. Median of 3 alternating rounds."
        table={profileTable}
      />
      <Findings>
        <li>
          <strong>The profile confirms the likely causes.</strong> Parsing the timestamps the median
          loaded was the largest Python cost of a summary miss, and a scores hit cost as much as a
          miss because it unpickled and rendered the whole body.
        </li>
        <li>
          <strong>A stale-statistics trap is gone.</strong> With stale planner statistics, the
          battery query scanned every owner's rows: 73.7 ms, against 5.3 ms with the owner on the
          join. With normal statistics both take 4.3 ms.
        </li>
        <li>
          <strong>The indexes cost little.</strong> A submit-style update went from about 0.266 to
          0.277 ms per row.
        </li>
      </Findings>
    </Section>
  )
}

export function SplitTab() {
  return (
    <Section title="What splitting into two services did">
      <Prose>
        The backend became two services, <code>catalog</code> and <code>instances</code>, behind a
        gateway. At the same fixed rates it cost <strong>no measurable latency or CPU</strong>,
        despite the extra hop. <strong>Peak capacity isn't shown to have moved:</strong> one mixed
        stress run reached ~581 req/s, against ~430 to ~573 before. The real cost is what has to
        run: 5 app-tier cores instead of 2, and about twice the memory in use. The gain is that
        respondents keep working while <code>catalog</code> is down.
      </Prose>
      <TableCard
        title="Holding 5 minutes at a fixed rate, one run each"
        description="No failed or dropped requests in any of the four. CPU and memory are one reading, 5 minutes in. The differences are small enough to be run-to-run variation."
        table={splitHoldTable}
      />
      <TableCard
        title="Stress, mixed traffic, at matching rates"
        description="Each cell is before / after the split. Busiest app container is saas-app before and saas-instances after."
        table={splitStressTable}
      />
      <TableCard title="What each deploy runs" table={splitDeployTable} />
      <Findings>
        <li>
          <strong>Respondents survived the outage.</strong> With <code>catalog</code> stopped for
          about two-thirds of a 3-minute run, 900 of 900 share-link opens and 900 of 900 submits
          succeeded. Logging in failed, as expected, and worked again once it returned.
        </li>
        <li>
          <strong>Queued events caught up.</strong> With <code>instances</code> stopped, 4 type
          changes waited in the outbox, and it was empty within 24 seconds of the restart.
        </li>
        <li>
          <strong>One service does nearly all the work.</strong> Under this traffic{" "}
          <code>instances</code> used about 0.8 cores and <code>catalog</code> about 0.05, so the
          extra cores aren't what carried the load.
        </li>
        <li>
          <strong>The break looks the same as before.</strong> Latency was steady, then within 15
          seconds k6 hit its limit of 300 VUs, with CPU to spare. Read-mostly traffic reached ~431
          req/s, in one run with no comparable earlier run.
        </li>
        <li>
          <strong>The one failed request is here.</strong> A connection reset from saas-instances
          during the mixed stress run, whose cause wasn't found.
        </li>
      </Findings>
    </Section>
  )
}

export function MethodTab() {
  return (
    <div className="grid items-start gap-6 lg:grid-cols-2">
      <Card className="gap-2" role="region" aria-label="Still open">
        <CardHeader>
          <CardTitle>Still open</CardTitle>
        </CardHeader>
        <CardContent>
          <Findings>
            <li>
              <strong>Find the next limit.</strong> The last soak was stopped at minute 45, so run
              one until it gives out.
            </li>
            <li>
              <strong>Explain the variation.</strong> The same test on the same code ended at ~430,
              ~497 and ~573 req/s, and the same 15-minute soak held saas-app at 78 % in one run and
              60 % in the other. Brief stalls well under the knee, and sudden collapses with CPU to
              spare, are part of it. They aren't from the cache, as the worst was with it off.
              Something below the app is suspected but not confirmed. Until this is understood, a
              single knee can't prove a gain under about 100 req/s.
            </li>
            <li>
              <strong>Make a cache miss cheaper.</strong> On the deploy it still takes 124 to 179 ms
              at about 18,000 rows per owner, and low-traffic owners rarely get a hit. A scores miss
              still reads every row in the window for its totals.
            </li>
            <li>
              <strong>Resize the app tier.</strong> saas-instances is now the busiest container, and{" "}
              <code>catalog</code> uses about 3 % of its 2 cores. Moving cores across hasn't been
              tried.
            </li>
            <li>
              <strong>Soak the split.</strong> Only short runs from reset data have been measured so
              far, and the cause of its one connection reset wasn't found.
            </li>
            <li>
              <strong>Pre-allocate k6's VUs.</strong> New VUs log in during a slowdown, which may
              feed the break and make the knee partly a test artefact.
            </li>
          </Findings>
        </CardContent>
      </Card>
      <Card className="gap-2" role="region" aria-label="How this was measured">
        <CardHeader>
          <CardTitle>How this was measured</CardTitle>
        </CardHeader>
        <CardContent>
          <Findings>
            <li>
              <strong>Deploy:</strong> unprivileged LXC containers on one Proxmox host. saas-app has
              2 cores and 2 GB, saas-db 2 cores and 1 GB (Postgres 16), and k6 runs from its own
              container. saas-cache (1 core, 512 MB, Redis 7) was added for the cache runs. The
              split added saas-instances (2 cores, 2 GB) and saas-gateway (1 core, 512 MB, nginx),
              and saas-app now runs only <code>catalog</code>.
            </li>
            <li>
              <strong>Data:</strong> every measured run starts from{" "}
              <code>just loadtest-reset</code>: 20 owners × 200 questionnaires. Runs add rows, so
              only runs with the same settings compare cleanly.
            </li>
            <li>
              <strong>Mixed traffic:</strong> 50 % owner reads, 30 % respondent flow, 15 % battery
              create, 5 % health check. <strong>Read-mostly</strong> is <code>MIX=read</code>.
            </li>
            <li>
              <strong>Stress:</strong> the rate rises every minute until p95 passes 1 s, failures
              pass 1 %, or k6 drops 1,000 iterations. <strong>Slowest group</strong> is the worst
              p95 among the endpoint groups.
            </li>
            <li>
              <strong>Dropped iterations:</strong> every soak drops some in its first 30 seconds
              (417 to 1,050) while k6's users log in. These are left out of drop counts "after
              startup".
            </li>
            <li>
              <strong>Latency:</strong> before 4 November, k6 reported p95 calculated from the start
              of each run. Each minute's mean could still be recovered from its running totals, so
              charts show means for every run. Newer runs send histograms, which also give true
              per-minute p95.
            </li>
            <li>
              <strong>Sources:</strong> the write-ups in <code>loadtest/baselines/</code>,
              per-minute figures from <code>just k6-report &lt;testid&gt;</code>. This page is
              updated by hand when a baseline is added.
            </li>
          </Findings>
        </CardContent>
      </Card>
    </div>
  )
}
