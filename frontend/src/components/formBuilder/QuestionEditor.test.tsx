import { render, screen, fireEvent } from "@testing-library/react"
import { vi } from "vitest"
import { QuestionEditor } from "@/components/formBuilder/QuestionEditor"
import type { BuilderQuestion } from "@/lib/formBuilder"

const textQuestion: BuilderQuestion = {
  name: "q1",
  title: "Your name",
  type: "text",
  required: false,
}

beforeEach(() => vi.clearAllMocks())

describe("QuestionEditor", () => {
  it("renders question title and name fields", () => {
    const onChange = vi.fn()
    render(<QuestionEditor question={textQuestion} onChange={onChange} />)
    expect(screen.getByDisplayValue("Your name")).toBeInTheDocument()
    expect(screen.getByDisplayValue("q1")).toBeInTheDocument()
  })

  it("calls onChange when title is changed", () => {
    const onChange = vi.fn()
    render(<QuestionEditor question={textQuestion} onChange={onChange} />)
    const titleInput = screen.getByLabelText(/question text/i)
    fireEvent.change(titleInput, { target: { value: "New title" } })
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ title: "New title" }))
  })

  it("hides choices textarea for text type", () => {
    const onChange = vi.fn()
    render(<QuestionEditor question={textQuestion} onChange={onChange} />)
    expect(screen.queryByTestId("choices-textarea")).not.toBeInTheDocument()
  })

  it("shows choices textarea for radiogroup type", () => {
    const onChange = vi.fn()
    const radioQ: BuilderQuestion = {
      ...textQuestion,
      type: "radiogroup",
      choices: ["A", "B"],
    }
    render(<QuestionEditor question={radioQ} onChange={onChange} />)
    expect(screen.getByTestId("choices-textarea")).toBeInTheDocument()
  })

  it("shows rating fields for rating type", () => {
    const onChange = vi.fn()
    const ratingQ: BuilderQuestion = {
      ...textQuestion,
      type: "rating",
      rateMin: 1,
      rateMax: 5,
    }
    render(<QuestionEditor question={ratingQ} onChange={onChange} />)
    expect(screen.getByTestId("rate-min-input")).toBeInTheDocument()
    expect(screen.getByTestId("rate-max-input")).toBeInTheDocument()
  })

  it("hides rating fields for non-rating type", () => {
    const onChange = vi.fn()
    render(<QuestionEditor question={textQuestion} onChange={onChange} />)
    expect(screen.queryByTestId("rate-min-input")).not.toBeInTheDocument()
  })

  it("calls onChange with updated choices", () => {
    const onChange = vi.fn()
    const radioQ: BuilderQuestion = {
      ...textQuestion,
      type: "radiogroup",
      choices: ["A"],
    }
    render(<QuestionEditor question={radioQ} onChange={onChange} />)
    const textarea = screen.getByTestId("choices-textarea")
    fireEvent.change(textarea, { target: { value: "A\nB\nC" } })
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ choices: ["A", "B", "C"] }))
  })

  it("shows duplicate name error when duplicateName is true", () => {
    const onChange = vi.fn()
    render(<QuestionEditor question={textQuestion} onChange={onChange} duplicateName />)
    expect(screen.getByTestId("duplicate-name-error")).toBeInTheDocument()
  })

  it("does not show duplicate name error by default", () => {
    const onChange = vi.fn()
    render(<QuestionEditor question={textQuestion} onChange={onChange} />)
    expect(screen.queryByTestId("duplicate-name-error")).not.toBeInTheDocument()
  })

  it("shows colCount select for radiogroup type", () => {
    const onChange = vi.fn()
    const radioQ: BuilderQuestion = {
      ...textQuestion,
      type: "radiogroup",
      choices: ["A", "B"],
      colCount: -1,
    }
    render(<QuestionEditor question={radioQ} onChange={onChange} />)
    expect(screen.getByTestId("col-count-select")).toBeInTheDocument()
  })

  it("shows colCount select for checkbox type", () => {
    const onChange = vi.fn()
    const checkQ: BuilderQuestion = {
      ...textQuestion,
      type: "checkbox",
      choices: ["A"],
      colCount: -1,
    }
    render(<QuestionEditor question={checkQ} onChange={onChange} />)
    expect(screen.getByTestId("col-count-select")).toBeInTheDocument()
  })

  it("does not show colCount select for text type", () => {
    const onChange = vi.fn()
    render(<QuestionEditor question={textQuestion} onChange={onChange} />)
    expect(screen.queryByTestId("col-count-select")).not.toBeInTheDocument()
  })

  it("does not show colCount select for dropdown type", () => {
    const onChange = vi.fn()
    const dropdownQ: BuilderQuestion = {
      ...textQuestion,
      type: "dropdown",
      choices: ["A"],
    }
    render(<QuestionEditor question={dropdownQ} onChange={onChange} />)
    expect(screen.queryByTestId("col-count-select")).not.toBeInTheDocument()
  })
})
