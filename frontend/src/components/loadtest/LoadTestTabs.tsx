import { Link } from "@tanstack/react-router"
import { ChartCard } from "@/components/dashboard/ChartCard"
import { Findings, Prose, Section, TableCard, TableDetails } from "@/components/loadtest/parts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useSeriesPalette } from "@/hooks/useChartPalette"
import {
  barsHeight,
  catalogGroupOption,
  catalogKneeOption,
  cacheKneesOption,
  cacheMixedOption,
  cacheReadOption,
  changesOption,
  changesTable,
  dbCpuOption,
  endpointMixedOption,
  endpointReadOption,
  fastapiHoldOption,
  fastapiKneeOption,
  fixesCpuOption,
  fixesOption,
  hitRatioOption,
  holdCpuOption,
  holdOption,
  kneeCpuOption,
  kneeLatencyOption,
  mongoCpuOption,
  mongoKneeOption,
  mongoLatencyOption,
  mongoSoakCpuOption,
  mongoSoakLatencyOption,
  nearPeakCpuOption,
  nearPeakOption,
  postgresRowsOption,
  profileHitOption,
  profileMissOption,
  profilePythonOption,
  rampAppCpuOption,
  rampDbCpuOption,
  rampOption,
  rampTable,
  readsHitOption,
  readsMissOption,
  soakCpuOption,
  soakDbCpuOption,
  soakDroppedOption,
  soakLatencyOption,
  splitCpuOption,
  splitLatencyOption,
  splitMemoryOption,
  splitSoakCpuOption,
  splitSoakLatencyOption,
  splitStressCpuOption,
  splitStressMeanOption,
  splitStressP95Option,
  trueP95CpuOption,
  trueP95LatencyOption,
} from "@/lib/loadtestCharts"
import {
  CHANGES,
  catalogAloneTable,
  catalogGroupTable,
  catalogKneeTable,
  failureTable,
  fastapiBugTable,
  fastapiHoldTable,
  fastapiKneeTable,
  fastapiSoakTable,
  holdTable,
  matchingTable,
  mongoHoldTable,
  mongoResultsTable,
  mongoSoakTable,
  mongoStressTable,
  profileTable,
  readsTable,
  splitDeployTable,
  splitFullTable,
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
          height={barsHeight(CHANGES.length, 1)}
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
        <div className="grid gap-6 lg:grid-cols-2">
          <ChartCard
            title="p95 at each knee, ms"
            description="Since run start."
            option={kneeLatencyOption(palette)}
            height={barsHeight(CHANGES.length, 2)}
          />
          <ChartCard
            title="CPU at each knee, %"
            option={kneeCpuOption(palette)}
            height={barsHeight(CHANGES.length, 2)}
          />
        </div>
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
        <div className="grid gap-6 lg:grid-cols-2">
          <ChartCard
            title="saas-app CPU, %, by request rate"
            option={rampAppCpuOption(palette)}
            height={340}
          />
          <ChartCard
            title="saas-db CPU, %, by request rate"
            option={rampDbCpuOption(palette)}
            height={340}
          />
        </div>
        <TableDetails table={rampTable} />
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
        <Prose>
          <strong>At matching rates:</strong> k6 p95 per endpoint in ms, since run start, so an
          earlier stall inflates the read-off column. Only the first three endpoints are cached: the
          others speed up because Postgres is less busy. Mixed compares 375 req/s off with 380 on,
          and read-mostly compares 360 req/s with 360.
        </Prose>
        <div className="grid gap-6 lg:grid-cols-2">
          <ChartCard
            title="Mixed traffic: p95 per endpoint, ms"
            option={endpointMixedOption(palette)}
            height={barsHeight(5, 2)}
          />
          <ChartCard
            title="Read-mostly traffic: p95 per endpoint, ms"
            option={endpointReadOption(palette)}
            height={barsHeight(5, 2)}
          />
        </div>
        <div className="grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
          <ChartCard
            title="Postgres rows read per second"
            option={postgresRowsOption(palette)}
            height={barsHeight(2, 2)}
          />
          <ChartCard
            title="saas-db CPU, %"
            option={dbCpuOption(palette)}
            height={barsHeight(2, 2)}
          />
          <ChartCard
            title="Cache hit ratio, %"
            option={hitRatioOption(palette)}
            height={barsHeight(2, 2)}
          />
        </div>
        <TableDetails table={matchingTable} />
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
          <ChartCard
            title="saas-db CPU, %, by minute"
            option={soakDbCpuOption(palette)}
            height={300}
          />
          <ChartCard
            title="Iterations dropped per minute"
            description="These miss a counter's first jump, so they add up to less than the run's total of 7,074."
            option={soakDroppedOption(palette)}
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
        <div className="grid gap-6 lg:grid-cols-2">
          <ChartCard
            title="Mean latency, ms, by minute, at ~215 req/s"
            option={holdOption(palette)}
            height={280}
          />
          <ChartCard
            title="saas-app CPU, %, by minute, at ~215 req/s"
            option={holdCpuOption(palette)}
            height={280}
          />
        </div>
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
      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard
          title="Stress: mean latency, ms, by request rate"
          option={fixesOption(palette)}
          height={340}
        />
        <ChartCard
          title="Stress: saas-app CPU, %, by request rate"
          option={fixesCpuOption(palette)}
          height={340}
        />
      </div>

      <h3 className="font-medium">True per-minute p95, stress run 3</h3>
      <Prose>
        The first run with histograms, so there is no earlier figure to compare with. Slowest
        endpoint group in each minute.
      </Prose>
      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard title="Latency, ms, by request rate" option={trueP95LatencyOption(palette)} height={300} />
        <ChartCard title="CPU, %, by request rate" option={trueP95CpuOption(palette)} height={300} />
      </div>
      <TableDetails table={trueP95Table} />

      <h3 className="font-medium">15 minutes near peak rate</h3>
      <Prose>
        ~445 req/s, about 10,000 new questionnaires a minute, reaching about 150,000 rows. Both from
        reset data, same code and command. Neither reached the stop rule and no request failed. Run
        1 dropped 2,280 iterations in minutes 6 to 9 (saas-app at 82–90 % CPU), then recovered at
        about 78 %. Run 2 held about 60 % CPU and dropped none after startup.
      </Prose>
      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard title="Mean latency, ms, by minute" option={nearPeakOption(palette)} height={300} />
        <ChartCard title="saas-app CPU, %, by minute" option={nearPeakCpuOption(palette)} height={300} />
      </div>

      <h3 className="font-medium">One owner's reads on the deploy, at the end of each soak</h3>
      <Prose>
        Median of 3 for the later run, with no other traffic. That owner has 18,416 questionnaires;
        the earlier one had 15,346.
      </Prose>
      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard title="Cache miss, ms" option={readsMissOption(palette)} height={barsHeight(3, 2)} />
        <ChartCard title="Cache hit, ms" option={readsHitOption(palette)} height={barsHeight(3, 2)} />
      </div>
      <TableDetails table={readsTable} />

      <h3 className="font-medium">Profile of a cache miss</h3>
      <Prose>
        A throwaway Postgres on the dev host, so read these as ratios. 300,000 questionnaires, the
        owner has 15,000, cache off. Median of 3 alternating rounds.
      </Prose>
      <div className="grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
        <ChartCard title="Miss, ms" option={profileMissOption(palette)} height={barsHeight(4, 2)} />
        <ChartCard title="Miss, Python CPU, ms" option={profilePythonOption(palette)} height={barsHeight(4, 2)} />
        <ChartCard title="Hit, ms" option={profileHitOption(palette)} height={barsHeight(4, 2)} />
      </div>
      <TableDetails table={profileTable} />

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
  const palette = useSeriesPalette()
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
      <h3 className="font-medium">Holding 5 minutes at a fixed rate, one run each</h3>
      <Prose>
        No failed or dropped requests in any of the four. CPU and memory are one reading, 5 minutes
        in. The differences are small enough to be run-to-run variation.
      </Prose>
      <div className="grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
        <ChartCard title="Latency, ms" option={splitLatencyOption(palette)} height={barsHeight(4, 2)} />
        <ChartCard title="CPU, in cores" option={splitCpuOption(palette)} height={barsHeight(4, 2)} />
        <ChartCard title="App-tier memory in use, MB" option={splitMemoryOption(palette)} height={barsHeight(4, 2)} />
      </div>
      <TableDetails table={splitHoldTable} />

      <h3 className="font-medium">Stress, mixed traffic, at matching rates</h3>
      <Prose>
        Each table cell is before / after the split. Busiest app container is saas-app before and
        saas-instances after.
      </Prose>
      <div className="grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
        <ChartCard title="Mean latency, ms" option={splitStressMeanOption(palette)} height={300} />
        <ChartCard title="Slowest group p95, ms" option={splitStressP95Option(palette)} height={300} />
        <ChartCard title="Busiest app container CPU, %" option={splitStressCpuOption(palette)} height={300} />
      </div>
      <TableDetails table={splitStressTable} />

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
          <strong>The one failed request was a connection reset,</strong> since found and fixed
          (see below).
        </li>
      </Findings>

      <h3 className="font-medium">Full baseline on the split, 5 and 6 November</h3>
      <Prose>
        All seven scenarios, on the same 2 + 2 cores, with 0 failed requests in every run. The host
        was busier than for the earlier runs, so fixed-rate latency reads higher, and other work on
        it may explain that.
      </Prose>
      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard title="Soak, mean latency, ms" option={splitSoakLatencyOption(palette)} height={300} />
        <ChartCard title="Soak, busiest app container CPU, %" option={splitSoakCpuOption(palette)} height={300} />
      </div>
      <TableCard title="Results" table={splitFullTable} />
      <Findings>
        <li>
          <strong>The split held an hour at 350 req/s.</strong> Rows grew from 4,000 to about
          478,000, with no failed request. Before the split the same soak began to slow at minute
          42 and was stopped at 45. The split stayed level to the end, though that is one run of
          each.
        </li>
        <li>
          <strong>Logging in sets the limit.</strong> Every stress run, and the soak at minute 45,
          slowed when many k6 users logged in at once. Logins hash passwords on{" "}
          <code>catalog</code>, while <code>instances</code> had CPU to spare.
        </li>
        <li>
          <strong>Moving a core didn't pay.</strong> On 1 + 3 cores logins were about 10 times
          slower under load, and the gain on <code>instances</code> was within run-to-run
          variation, so the deploy stays on 2 + 2.
        </li>
        <li>
          <strong>The connection reset is fixed.</strong> gunicorn closed idle connections after 2
          seconds while nginx kept them for 60, and a reused one could be reset. A test that aimed
          at this gave 306 failures in 19,120 requests before the fix and none after.
        </li>
      </Findings>
    </Section>
  )
}

export function MongoTab() {
  const palette = useSeriesPalette()
  return (
    <Section title="Postgres against MongoDB for instances">
      <Prose>
        <code>instances</code> ran on MongoDB 8.0 with the same 2 cores and 1 GB as Postgres, through{" "}
        <code>django-mongodb-backend</code>, and every scenario ran on each engine back to back. Both
        gave <strong>0 failed requests</strong> in every run, and respondents kept working with{" "}
        <code>catalog</code> down. But <strong>MongoDB was slower, and got slower as rows grew</strong>:
        the mixed stress knee fell from ~575–614 to ~322–332 req/s, and the 1-hour soak was stopped at
        minute 18. <code>instances</code> stays on Postgres, and the MongoDB support was removed.
      </Prose>

      <h3 className="font-medium">Holding 5 minutes at a fixed rate, one run each</h3>
      <Prose>
        MongoDB's p95 was nearly twice Postgres's under mixed traffic. Its database CPU also rose every
        minute at a constant rate, from 16 to 28 %, where Postgres's stayed near 9 %.
      </Prose>
      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard title="Latency, ms" option={mongoLatencyOption(palette)} height={barsHeight(4, 2)} />
        <ChartCard title="Database CPU, %" option={mongoCpuOption(palette)} height={barsHeight(2, 2)} />
      </div>
      <TableDetails table={mongoHoldTable} />

      <h3 className="font-medium">Stress and soak</h3>
      <div className="grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
        <ChartCard title="Knee per stress run, req/s" option={mongoKneeOption(palette)} height={barsHeight(10, 1)} />
        <ChartCard title="Soak, slowest group p95, ms" option={mongoSoakLatencyOption(palette)} height={300} />
        <ChartCard title="Soak, database CPU, %" option={mongoSoakCpuOption(palette)} height={300} />
      </div>
      <TableDetails table={mongoStressTable} />
      <TableDetails table={mongoSoakTable} />
      <TableCard title="Other runs" table={mongoResultsTable} />
      <Findings>
        <li>
          <strong>The first runs collapsed, from two translation problems.</strong> The backend builds
          unique indexes as partial, which cannot find a null, so each questionnaire with no battery
          scanned every battery: 2.8 million documents read to return 10 rows. And it joins every
          matching row before it sorts and limits a page. Fixing both took p95 at a fixed rate from
          5.27 s to 16 ms.
        </li>
        <li>
          <strong>What is left grows with rows.</strong> Dashboard cache misses still join every row in
          their window before keeping 10 or 500, which Postgres's planner avoids. That is what set
          MongoDB's knee, with both containers' CPU to spare, and what slowed the soak.
        </li>
        <li>
          <strong>MongoDB needs its own code paths.</strong> Transactions, the double-submit guard,
          list joins and index shapes all differ by engine already, and each remaining slow query
          would need another.
        </li>
        <li>
          <strong>It does save disk.</strong> Compressed data took about half the space, though its
          indexes, with UUIDs stored as text, were no smaller.
        </li>
      </Findings>
    </Section>
  )
}

export function FastapiTab() {
  const palette = useSeriesPalette()
  return (
    <Section title="catalog on FastAPI against Django">
      <Prose>
        <code>catalog</code> was rewritten on FastAPI with the same API, tables and events, and ran on the
        same container as Django did. On <code>catalog</code>'s own traffic, with four bugs fixed,{" "}
        <strong>FastAPI is faster</strong>: its knee is ~532 to ~594 req/s against Django's ~409 to ~431, and at the
        same rate its p95 is 16.5 ms against 27.6 ms, at 25 % CPU against 41 %. Logins, mostly the password
        hash, are the same on both. On the whole app's traffic, where <code>catalog</code> is nearly idle,
        the two looked the same. <code>catalog</code> stays on FastAPI, and the Django version was removed.
      </Prose>

      <h3 className="font-medium">catalog's own traffic</h3>
      <Prose>
        A k6 scenario that calls only <code>catalog</code>: lists, details, <code>/me</code>, token refresh,
        and creating, editing and deleting types. Django ran from its last commit. The first FastAPI runs
        reached less than half Django's knee, from two bugs the whole-app traffic never reached: the signing
        key was parsed for every token (25 ms each), and every call to <code>instances</code> built a new
        HTTP client, which also leaked memory.
      </Prose>
      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard title="Knee per stress run, req/s" option={catalogKneeOption(palette)} height={barsHeight(8, 1)} />
        <ChartCard title="p95 per group at ~240 req/s, ms" option={catalogGroupOption(palette)} height={barsHeight(8, 2)} />
      </div>
      <TableDetails table={catalogKneeTable} />
      <TableDetails table={catalogGroupTable} />
      <TableCard title="catalog alone, final code" table={catalogAloneTable} />

      <h3 className="font-medium">The whole app's traffic</h3>

      <h3 className="font-medium">Holding 5 minutes at a fixed rate, one run each</h3>
      <Prose>
        At this rate <code>catalog</code> gets about 30 req/s and uses about 3 % CPU on either, so the
        differences are under a millisecond, with no direction that holds across both mixes.
      </Prose>
      <ChartCard title="catalog p95, ms" option={fastapiHoldOption(palette)} height={barsHeight(4, 2)} />
      <TableDetails table={fastapiHoldTable} />

      <h3 className="font-medium">Stress and soak</h3>
      <Prose>
        Django's knees are from 2026-11-06, the closest runs in time; FastAPI's ran on the final code.
        Each run broke the same way: <code>instances</code> reached 80 to 90 % CPU, k6 added users, and
        they all logged in at once.
      </Prose>
      <ChartCard title="Knee per stress run, req/s" option={fastapiKneeOption(palette)} height={barsHeight(8, 1)} />
      <TableDetails table={fastapiKneeTable} />
      <TableCard title="1-hour soak" table={fastapiSoakTable} />

      <h3 className="font-medium">What the stress runs found</h3>
      <TableCard title="Failed requests by version of the code" table={fastapiBugTable} />
      <Findings>
        <li>
          <strong>A request held a connection while it waited for a thread.</strong> The login check kept
          its database connection while the endpoint waited for one of the worker's 40 threads. Under load,
          every thread waited for one of the 15 connections, and the worker stalled until the 30-second
          pool timeout. It now hands the connection back first.
        </li>
        <li>
          <strong>Logins held a connection through the password hash</strong>, hundreds of milliseconds
          of CPU each. A burst of logins took all 15. Logins now release it before hashing, and each worker
          runs at most 15 threads, so extra requests queue instead of failing.
        </li>
        <li>
          <strong>Django never hit either</strong>, because each of its threads had its own connection.
          Both bugs have tests that reproduce them with 2 threads and 1 connection.
        </li>
        <li>
          <strong>Logins are slower in a burst.</strong> When k6 logs every user in again, FastAPI runs up
          to 15 hashes per worker at once against Django's 4, on the same 2 cores, so each login waits longer.
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
              <strong>Find the next limit.</strong> The split held a 1-hour soak, so where it gives
              out past about 478,000 rows is still unknown. A 3-hour soak would find it.
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
              <strong>Pre-allocate k6's VUs.</strong> New VUs log in during a slowdown, and on the
              split those logins on <code>catalog</code> are what break every stress run. The knee
              is partly a test artefact until this is tried.
            </li>
            <li>
              <strong>Keep the host quiet.</strong> Other work on the same host matched the slowest
              runs, but this was never proven. A run on a quiet host, or one with its own cores,
              would settle how much of the variation it causes.
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
