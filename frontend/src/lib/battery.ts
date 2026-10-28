import type { PublicBattery, PublicBatterySlot } from "@/types/questionnaires"

/** The first unsubmitted slot in battery order, or `undefined` when all are done. */
export function nextSlot(battery: PublicBattery): PublicBatterySlot | undefined {
  return [...battery.questionnaires]
    .sort((a, b) => a.order - b.order)
    .find((slot) => slot.submittedAt === null)
}

export function slotProgress(slots: { submittedAt: string | null }[]) {
  const done = slots.filter((s) => s.submittedAt !== null).length
  return { done, total: slots.length }
}
