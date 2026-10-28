import { describe, expect, it } from "vitest"
import { moveItem, removeAt } from "./list"

describe("moveItem", () => {
  it("moves up and down", () => {
    expect(moveItem(["a", "b", "c"], 1, -1)).toEqual(["b", "a", "c"])
    expect(moveItem(["a", "b", "c"], 1, 1)).toEqual(["a", "c", "b"])
  })

  it("clamps at the ends", () => {
    expect(moveItem(["a", "b"], 0, -1)).toEqual(["a", "b"])
    expect(moveItem(["a", "b"], 1, 1)).toEqual(["a", "b"])
  })

  it("does not mutate the input", () => {
    const items = ["a", "b"]
    moveItem(items, 0, 1)
    expect(items).toEqual(["a", "b"])
  })
})

describe("removeAt", () => {
  it("removes one element", () => {
    expect(removeAt(["a", "b", "c"], 1)).toEqual(["a", "c"])
  })
})
