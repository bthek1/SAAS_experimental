/**
 * CSS variable token names for the design system.
 * Use getCSSVar() to read resolved values at runtime (e.g. for ECharts theming).
 */
export const themeTokens = {
  background: "--background",
  foreground: "--foreground",
  primary: "--primary",
  primaryForeground: "--primary-foreground",
  secondary: "--secondary",
  muted: "--muted",
  mutedForeground: "--muted-foreground",
  accent: "--accent",
  destructive: "--destructive",
  border: "--border",
  chart1: "--chart-1",
  chart2: "--chart-2",
  chart3: "--chart-3",
  chart4: "--chart-4",
  chart5: "--chart-5",
  card: "--card",
  series1: "--series-1",
  series2: "--series-2",
  series3: "--series-3",
  series4: "--series-4",
  series5: "--series-5",
  series6: "--series-6",
  series7: "--series-7",
  seriesOff: "--series-off",
} as const;

export type ThemeToken = keyof typeof themeTokens;

/** Read the resolved CSS variable value for a given token. */
export function getCSSVar(token: ThemeToken): string {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(themeTokens[token])
    .trim();
}
