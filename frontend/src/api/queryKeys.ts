import type { DashboardParams, DashboardScoresParams } from "@/types/dashboard";
import type { QuestionnaireFilters } from "@/types/questionnaires";

export const queryKeys = {
  auth: {
    me: ["auth", "me"] as const,
    register: ["auth", "register"] as const,
  },
  health: ["health"] as const,
  tasks: {
    status: (taskId: string) => ["tasks", taskId] as const,
  },
  // Each resource's `all` is the prefix of every key below it, so invalidating
  // it refreshes the full list, every page and every detail.
  questionnaireTypes: {
    all: ["questionnaire-types"] as const,
    page: (page: number) => ["questionnaire-types", "page", page] as const,
    detail: (id: string) => ["questionnaire-types", id] as const,
  },
  questionnaires: {
    all: ["questionnaires"] as const,
    list: (filters: QuestionnaireFilters) => ["questionnaires", "list", filters] as const,
    page: (filters: QuestionnaireFilters, page: number) =>
      ["questionnaires", "page", filters, page] as const,
    detail: (id: string) => ["questionnaires", id] as const,
    byToken: (token: string) => ["public", "questionnaires", token] as const,
  },
  batteryTypes: {
    all: ["battery-types"] as const,
    page: (page: number) => ["battery-types", "page", page] as const,
    detail: (id: string) => ["battery-types", id] as const,
  },
  batteries: {
    all: ["batteries"] as const,
    page: (page: number) => ["batteries", "page", page] as const,
    detail: (id: string) => ["batteries", id] as const,
    byToken: (token: string) => ["public", "batteries", token] as const,
  },
  dashboard: {
    all: ["dashboard"] as const,
    summary: (params: DashboardParams) => ["dashboard", "summary", params] as const,
    scores: (params: DashboardScoresParams) => ["dashboard", "scores", params] as const,
  },
} as const;
