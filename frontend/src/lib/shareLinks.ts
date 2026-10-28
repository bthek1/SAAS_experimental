/** Public link a respondent opens to complete one questionnaire. */
export function takeUrl(shareToken: string): string {
  return `${window.location.origin}/take/${shareToken}`
}

/** Public link a respondent opens to complete every questionnaire in a battery. */
export function takeBatteryUrl(shareToken: string): string {
  return `${window.location.origin}/take-battery/${shareToken}`
}
