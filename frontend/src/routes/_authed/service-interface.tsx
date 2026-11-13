import { createFileRoute } from "@tanstack/react-router"
import { ArrowLeft, ArrowRight, Database, type LucideIcon } from "lucide-react"
import type { ReactNode } from "react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

export const Route = createFileRoute("/_authed/service-interface")({
  component: ServiceInterfacePage,
})

function Code({ children }: { children: ReactNode }) {
  return <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs whitespace-nowrap">{children}</code>
}

const SERVICES = [
  {
    name: "catalog",
    database: "Its own PostgreSQL database",
    summary: "The source of truth for who users are and what can be sent out.",
    owns: ["Users, login and tokens", "Questionnaire types", "Battery types", "The outbox of events"],
  },
  {
    name: "instances",
    database: "Its own PostgreSQL database",
    summary: "Everything made from a type, and what respondents send back.",
    owns: [
      "Questionnaires and batteries",
      "Share links and answers",
      "Dashboards and PDFs",
      "Read-only copies of types",
    ],
  },
]

interface Call {
  direction: "to-instances" | "to-catalog"
  method: string
  path: string
  purpose: string
}

const CALLS: Call[] = [
  {
    direction: "to-instances",
    method: "POST",
    path: "/internal/events/",
    purpose: "Delivers one event: a type or a user changed.",
  },
  {
    direction: "to-instances",
    method: "POST",
    path: "/internal/refs/<kind>/<id>/retire/",
    purpose: "Asks to remove a copy before its type is deleted. 409 means it is in use.",
  },
  {
    direction: "to-catalog",
    method: "GET",
    path: "/internal/<types>/<id>/",
    purpose: "Fetches one type whose copy has not arrived yet.",
  },
  {
    direction: "to-catalog",
    method: "GET",
    path: "/internal/<types>/?after=<id>",
    purpose: "Pages through every type, 500 at a time, for reconcile_refs.",
  },
]

function CallRow({ call }: { call: Call }) {
  const toInstances = call.direction === "to-instances"
  const Arrow: LucideIcon = toInstances ? ArrowRight : ArrowLeft
  return (
    <li className="rounded-lg border bg-card p-3">
      {/* Same order as the cards beside it. The arrow points at the service being called. */}
      <div
        role="img"
        aria-label={toInstances ? "catalog calls instances" : "instances calls catalog"}
        className="flex items-center gap-2 text-xs text-muted-foreground"
      >
        <span>catalog</span>
        <Arrow className="h-3.5 w-3.5 shrink-0" />
        <span>instances</span>
      </div>
      <p className="mt-1 font-mono text-xs font-medium break-words">
        {call.method} {call.path}
      </p>
      <p className="mt-1 text-sm text-muted-foreground">{call.purpose}</p>
    </li>
  )
}

function ServiceCard({ service }: { service: (typeof SERVICES)[number] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-mono">{service.name}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p>{service.summary}</p>
        <ul className="list-disc space-y-1 pl-4 text-muted-foreground">
          {service.owns.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Database className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {service.database}
        </p>
      </CardContent>
    </Card>
  )
}

const FLOWS: { title: string; steps: ReactNode[] }[] = [
  {
    title: "A type is saved",
    steps: [
      <>
        <Code>catalog</Code> saves the type, raises its version and writes an event to the outbox, all
        in one transaction.
      </>,
      "After the commit, it tries to deliver the event once. A failed delivery does not fail the save.",
      <>
        <Code>relay-outbox</Code> retries anything undelivered every 5 seconds, oldest first.
      </>,
      <>
        <Code>instances</Code> updates its copy if the event's version is newer, and ignores it
        otherwise. Duplicates and late arrivals change nothing.
      </>,
    ],
  },
  {
    title: "A type's copy has not arrived yet",
    steps: [
      "An owner creates a questionnaire or battery from a type that instances has no copy of.",
      <>
        <Code>instances</Code> asks <Code>catalog</Code> for that type and stores the answer.
      </>,
      "If catalog has no such type, or another owner holds it, the request fails validation as usual.",
      "If catalog cannot be reached, the owner gets a 503, because the id may well be valid.",
    ],
  },
  {
    title: "A type is deleted",
    steps: [
      <>
        <Code>catalog</Code> refuses with a 409 if a battery type still includes the questionnaire type.
      </>,
      <>
        It then asks <Code>instances</Code> to retire the copy. A database restriction there refuses
        with a 409 if anything was made from it.
      </>,
      "If instances cannot answer, the owner gets a 503 and nothing is deleted.",
      "On success, the type is deleted and a deleted event is queued. A tombstone stops late events from bringing the copy back.",
    ],
  },
  {
    title: "A user is deactivated or deleted",
    steps: [
      <>
        <Code>catalog</Code> queues a <Code>user.*</Code> event. It travels through the same outbox as
        type events.
      </>,
      <>
        <Code>instances</Code> records the owner in <Code>BlockedOwner</Code>, since it has no user table
        to check.
      </>,
      "The owner's requests to instances are then refused, even with a token that has not expired.",
      "A deleted user also loses their questionnaires, batteries and copies. Reactivating lifts the block.",
    ],
  },
]

const ENVELOPE_FIELDS = ["id", "type", "aggregateId", "version", "data"]

const EVENTS = [
  {
    type: "questionnaire_type.changed",
    when: "A questionnaire type was created or edited",
    data: "ownerId, title, createdAt, updatedAt, questionnaireJson",
  },
  {
    type: "battery_type.changed",
    when: "A battery type was created or edited",
    data: "ownerId, title, createdAt, updatedAt, description, items",
  },
  { type: "questionnaire_type.deleted", when: "A questionnaire type was deleted", data: "ownerId" },
  { type: "battery_type.deleted", when: "A battery type was deleted", data: "ownerId" },
  { type: "user.deactivated", when: "A user's account was turned off", data: "Empty" },
  { type: "user.reactivated", when: "A user's account was turned back on", data: "Empty" },
  { type: "user.deleted", when: "A user was deleted", data: "Empty" },
]

const OUTAGES = [
  {
    service: "catalog is down",
    works: [
      "Respondents open share links and submit answers",
      "Existing tokens keep working on instances, which verifies them with a public key",
      "Owners see questionnaires and dashboards, and create from types already copied",
    ],
    stops: [
      "Logging in and refreshing tokens",
      "Viewing or changing types",
      "Creating from a type with no copy yet (503)",
    ],
  },
  {
    service: "instances is down",
    works: ["Logging in", "Viewing, creating and editing types: their events wait in the outbox"],
    stops: [
      "Everything about questionnaires, batteries and dashboards",
      "Deleting a type (503, and nothing is deleted)",
    ],
  },
]

const RULES: { title: string; body: ReactNode }[] = [
  {
    title: "Private to the services",
    body: (
      <>
        The gateway routes only public paths, so browsers cannot reach <Code>/internal/</Code>. On the
        deployed containers, the firewall also limits a service's port to the gateway, its peer and the
        metrics scraper.
      </>
    ),
  },
  {
    title: "One token per direction",
    body: (
      <>
        Each call carries a bearer token for its direction, compared in constant time. Only{" "}
        <Code>/internal/health/</Code> takes no token.
      </>
    ),
  },
  {
    title: "No shared code or tables",
    body: (
      <>
        Neither service imports the other, even in tests. <Code>common</Code> holds infrastructure and no
        models.
      </>
    ),
  },
  {
    title: "Tested from both sides",
    body: (
      <>
        <Code>backend/contracts/</Code> holds the JSON shapes. <Code>catalog</Code> proves it produces
        them and <Code>instances</Code> proves it accepts them.
      </>
    ),
  },
  {
    title: "Short timeouts",
    body: "A call waits 0.5 seconds to connect and 2 seconds to read by default. A 5xx, 401 or 403 counts as the peer being unavailable.",
  },
  {
    title: "A way to repair",
    body: (
      <>
        After a data move or a long outage, <Code>reconcile_refs</Code> rebuilds the copies from{" "}
        <Code>catalog</Code> and reports what differed. <Code>--dry-run</Code> only reports.
      </>
    ),
  },
]

function Section({ title, intro, children }: { title: string; intro?: ReactNode; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        {intro && <p className="text-sm text-muted-foreground">{intro}</p>}
      </div>
      {children}
    </section>
  )
}

function ServiceInterfacePage() {
  const [catalog, instances] = SERVICES

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Service interface</h1>
        <p className="text-sm text-muted-foreground">
          How <Code>catalog</Code> and <Code>instances</Code> work together without sharing a database.
        </p>
      </div>

      <Section
        title="Two services, four calls"
        intro={
          <>
            The browser reaches both through the gateway at <Code>/api/</Code>. Between themselves, they
            use only these calls. <Code>{"<types>"}</Code> is <Code>questionnaire-types</Code> or{" "}
            <Code>battery-types</Code>.
          </>
        }
      >
        <div className="grid items-start gap-4 lg:grid-cols-[1fr_minmax(0,1.5fr)_1fr]">
          <ServiceCard service={catalog} />
          <ul aria-label="Calls between the services" className="space-y-2">
            {CALLS.map((call) => (
              <CallRow key={call.path} call={call} />
            ))}
          </ul>
          <ServiceCard service={instances} />
        </div>
        <p className="text-sm text-muted-foreground">
          Login involves no call at all: <Code>catalog</Code> signs each token with its private key, and{" "}
          <Code>instances</Code> checks it with the public key. Questionnaires can therefore keep working
          while <Code>catalog</Code> is stopped.
        </p>
      </Section>

      <Section title="What happens when…">
        <div className="grid gap-4 md:grid-cols-2">
          {FLOWS.map((flow) => (
            <Card key={flow.title}>
              <CardHeader>
                <CardTitle>{flow.title}</CardTitle>
              </CardHeader>
              <CardContent>
                <ol className="list-decimal space-y-2 pl-4">
                  {flow.steps.map((step, index) => (
                    <li key={index}>{step}</li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          ))}
        </div>
      </Section>

      <Section
        title="Events"
        intro={
          <>
            Every event has the same envelope:{" "}
            {ENVELOPE_FIELDS.map((field, index) => (
              <span key={field}>
                {index > 0 && ", "}
                <Code>{field}</Code>
              </span>
            ))}
            . A type event carries the type's full state, so one event is enough to catch up.
          </>
        }
      >
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Event</TableHead>
                <TableHead>Sent when</TableHead>
                <TableHead>Fields in data</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {EVENTS.map((event) => (
                <TableRow key={event.type}>
                  <TableCell className="font-mono text-xs">{event.type}</TableCell>
                  <TableCell>{event.when}</TableCell>
                  <TableCell className="text-muted-foreground">{event.data}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Section>

      <Section title="When one service is down">
        <div className="grid gap-4 md:grid-cols-2">
          {OUTAGES.map((outage) => (
            <Card key={outage.service}>
              <CardHeader>
                <CardTitle className="font-mono">{outage.service}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <Badge variant="secondary">Keeps working</Badge>
                  <ul className="mt-2 list-disc space-y-1 pl-4">
                    {outage.works.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <Badge variant="outline">Stops</Badge>
                  <ul className="mt-2 list-disc space-y-1 pl-4">
                    {outage.stops.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </Section>

      <Section title="What keeps it safe">
        <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {RULES.map((rule) => (
            <div key={rule.title} className="rounded-lg border p-4">
              <dt className="text-sm font-medium">{rule.title}</dt>
              <dd className="mt-1 text-sm text-muted-foreground">{rule.body}</dd>
            </div>
          ))}
        </dl>
      </Section>
    </div>
  )
}
