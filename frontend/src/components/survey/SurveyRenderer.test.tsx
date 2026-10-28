import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { SurveyRenderer } from "./SurveyRenderer"

const survey = {
  showQuestionNumbers: "off",
  pages: [
    {
      name: "p1",
      elements: [{ type: "text", name: "age", title: "Your age", inputType: "number" }],
    },
  ],
  calculatedValues: [{ name: "doubled", expression: "{age} * 2" }],
}

describe("SurveyRenderer", () => {
  it("renders the questions", async () => {
    render(<SurveyRenderer surveyJson={survey} />)
    expect(await screen.findByText("Your age")).toBeInTheDocument()
  })

  it("passes answers and calculated metrics to onComplete", async () => {
    const onComplete = vi.fn()
    const user = userEvent.setup()
    render(<SurveyRenderer surveyJson={survey} onComplete={onComplete} />)

    await user.type(await screen.findByRole("spinbutton"), "21")
    await user.click(screen.getByRole("button", { name: /complete/i }))

    expect(onComplete).toHaveBeenCalledWith({ age: 21 }, { doubled: 42 })
  })

  it("shows existing answers read-only without a complete button", async () => {
    render(<SurveyRenderer surveyJson={survey} data={{ age: 30 }} readOnly />)
    expect(await screen.findByDisplayValue("30")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /complete/i })).not.toBeInTheDocument()
  })
})
