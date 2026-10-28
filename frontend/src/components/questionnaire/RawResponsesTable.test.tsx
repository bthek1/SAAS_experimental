import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"
import { submittedQuestionnaire } from "@/test/questionnaireFixtures"
import { RawResponsesTable } from "./RawResponsesTable"

describe("RawResponsesTable", () => {
  it("is collapsed until opened", async () => {
    const user = userEvent.setup()
    render(<RawResponsesTable responses={[submittedQuestionnaire]} />)
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /raw responses \(1\)/i }))
    expect(screen.getByRole("table")).toBeInTheDocument()
    expect(screen.getByText("Bob")).toBeInTheDocument()
  })

  it("truncates long answers and expands a row", async () => {
    const long = { ...submittedQuestionnaire, answers: { essay: "x".repeat(300) } }
    const user = userEvent.setup()
    render(<RawResponsesTable responses={[long]} />)
    await user.click(screen.getByRole("button", { name: /raw responses/i }))
    expect(screen.getByText(/…$/)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "View full" }))
    expect(screen.getByRole("button", { name: "View less" })).toBeInTheDocument()
    expect(screen.queryByText(/…$/)).not.toBeInTheDocument()
  })
})
