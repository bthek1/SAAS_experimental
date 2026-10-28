/** Return a copy of `items` with the element at `index` moved by `offset` (clamped). */
export function moveItem<T>(items: readonly T[], index: number, offset: number): T[] {
  const target = Math.min(Math.max(index + offset, 0), items.length - 1)
  if (index < 0 || index >= items.length || target === index) return [...items]
  const next = [...items]
  const [item] = next.splice(index, 1)
  next.splice(target, 0, item)
  return next
}

/** Return a copy of `items` without the element at `index`. */
export function removeAt<T>(items: readonly T[], index: number): T[] {
  return items.filter((_, i) => i !== index)
}
