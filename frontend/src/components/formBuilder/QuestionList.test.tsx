import { render, screen, fireEvent } from "@testing-library/react"
import { vi } from "vitest"
import { QuestionList } from "@/components/formBuilder/QuestionList"
import type { AnyQuestion } from "@/lib/formBuilder"

const textQ: AnyQuestion = { name: "q1", title: "Name", type: "text", required: false }
const radioQ: AnyQuestion = {
  name: "q2",
  title: "Colour",
  type: "radiogroup",
  required: false,
  choices: ["Red", "Blue"],
}
const advancedQ: AnyQuestion = {
  _advanced: true,
  name: "mx1",
  type: "matrix",
  raw: { type: "matrix", name: "mx1" },
}

const defaultProps = {
  questions: [textQ, radioQ],
  selectedIndex: null,
  onSelect: vi.fn(),
  onAdd: vi.fn(),
  onAddAt: vi.fn(),
  onDelete: vi.fn(),
  onDuplicate: vi.fn(),
  onMoveUp: vi.fn(),
  onMoveDown: vi.fn(),
}

beforeEach(() => vi.clearAllMocks())

describe("QuestionList", () => {
  it("renders question titles", () => {
    render(<QuestionList {...defaultProps} />)
    expect(screen.getByText("Name")).toBeInTheDocument()
    expect(screen.getByText("Colour")).toBeInTheDocument()
  })

  it("shows empty state when no questions", () => {
    render(<QuestionList {...defaultProps} questions={[]} />)
    expect(screen.getByTestId("empty-state")).toBeInTheDocument()
  })

  it("calls onSelect when a question is clicked", () => {
    render(<QuestionList {...defaultProps} />)
    fireEvent.click(screen.getByTestId("question-item-0"))
    expect(defaultProps.onSelect).toHaveBeenCalledWith(0)
  })

  it("calls onAdd when Add question button is clicked", () => {
    render(<QuestionList {...defaultProps} />)
    fireEvent.click(screen.getByTestId("add-question-btn"))
    expect(defaultProps.onAdd).toHaveBeenCalled()
  })

  it("calls onDelete when delete button is clicked", () => {
    render(<QuestionList {...defaultProps} />)
    const deleteBtns = screen.getAllByRole("button", { name: /delete question/i })
    fireEvent.click(deleteBtns[0])
    expect(defaultProps.onDelete).toHaveBeenCalledWith(0)
  })

  it("calls onMoveUp when move-up button is clicked", () => {
    render(<QuestionList {...defaultProps} />)
    const upBtns = screen.getAllByRole("button", { name: /move up/i })
    // second item can move up (first is disabled)
    fireEvent.click(upBtns[1])
    expect(defaultProps.onMoveUp).toHaveBeenCalledWith(1)
  })

  it("calls onMoveDown when move-down button is clicked", () => {
    render(<QuestionList {...defaultProps} />)
    const downBtns = screen.getAllByRole("button", { name: /move down/i })
    fireEvent.click(downBtns[0])
    expect(defaultProps.onMoveDown).toHaveBeenCalledWith(0)
  })

  it("disables move-up for first question", () => {
    render(<QuestionList {...defaultProps} />)
    const upBtns = screen.getAllByRole("button", { name: /move up/i })
    expect(upBtns[0]).toBeDisabled()
  })

  it("disables move-down for last question", () => {
    render(<QuestionList {...defaultProps} />)
    const downBtns = screen.getAllByRole("button", { name: /move down/i })
    expect(downBtns[downBtns.length - 1]).toBeDisabled()
  })

  it("renders advanced question with [Advanced] prefix", () => {
    render(<QuestionList {...defaultProps} questions={[advancedQ]} />)
    expect(screen.getByText("[Advanced] mx1")).toBeInTheDocument()
  })

  it("highlights selected question", () => {
    render(<QuestionList {...defaultProps} selectedIndex={0} />)
    expect(screen.getByTestId("question-item-0")).toHaveClass("border-primary")
  })
})
