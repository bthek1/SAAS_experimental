import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { ResultTableData } from "@/lib/loadtestResults"
import { ResultsTable, TableCard, TableDetails } from "./parts"

const table: ResultTableData = {
  columns: [
    { title: "Name" },
    { title: "Rate", num: true },
    { title: "Note", prose: true },
    { title: "Run", code: true },
  ],
  rows: [["First", 12, "A long note", "stress-1"]],
}

describe("ResultsTable", () => {
  it("renders every header and cell", () => {
    render(<ResultsTable table={table} />)
    for (const title of ["Name", "Rate", "Note", "Run"]) {
      expect(screen.getByRole("columnheader", { name: title })).toBeInTheDocument()
    }
    expect(screen.getByRole("cell", { name: "First" })).toBeInTheDocument()
  })

  it("right-aligns numbers, wraps prose and marks run ids as code", () => {
    render(<ResultsTable table={table} />)
    expect(screen.getByRole("cell", { name: "12" }).className).toContain("text-right")
    expect(screen.getByRole("cell", { name: "A long note" }).className).toContain("whitespace-normal")
    expect(screen.getByText("stress-1").tagName).toBe("CODE")
  })

  it("lets a numeric header wrap, so long titles do not widen the table", () => {
    render(<ResultsTable table={table} />)
    expect(screen.getByRole("columnheader", { name: "Rate" }).className).toContain("whitespace-normal")
  })
})

describe("TableCard", () => {
  it("is a labelled region with its description", () => {
    render(<TableCard title="The holds" description="One run each." table={table} />)
    const region = screen.getByRole("region", { name: "The holds" })
    expect(within(region).getByText("One run each.")).toBeInTheDocument()
    expect(within(region).getByRole("table")).toBeInTheDocument()
  })
})

describe("TableDetails", () => {
  it("is closed until asked for", () => {
    const { container } = render(<TableDetails table={table} />)
    expect(container.querySelector("details")).not.toHaveAttribute("open")
    expect(screen.getByText("Show the table").tagName).toBe("SUMMARY")
  })
})
