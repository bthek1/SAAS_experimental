import type { ReactNode } from "react"
import { ThemeToggle } from "@/components/ui/ThemeToggle"

/** Page frame for respondents: no navbar, sidebar or account UI. */
export function PublicShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      <header className="flex justify-end p-4">
        <ThemeToggle />
      </header>
      <main className="mx-auto max-w-3xl px-4 pb-16">{children}</main>
    </div>
  )
}

export function Notice({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-3 text-center">
      <h1 className="text-2xl font-semibold">{title}</h1>
      {children && <div className="text-muted-foreground">{children}</div>}
    </div>
  )
}
