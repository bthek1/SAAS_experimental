export const queryKeys = {
  auth: {
    me: ["auth", "me"] as const,
    register: ["auth", "register"] as const,
  },
  health: ["health"] as const,
  tasks: {
    status: (taskId: string) => ["tasks", taskId] as const,
  },
  questionnaireTypes: {
    all: ["questionnaire-types"] as const,
    detail: (id: string) => ["questionnaire-types", id] as const,
  },
  questionnaires: {
    all: ["questionnaires"] as const,
    detail: (id: string) => ["questionnaires", id] as const,
    byToken: (token: string) => ["public", "questionnaires", token] as const,
  },
  batteryTypes: {
    all: ["battery-types"] as const,
    detail: (id: string) => ["battery-types", id] as const,
  },
  batteries: {
    all: ["batteries"] as const,
    detail: (id: string) => ["batteries", id] as const,
    byToken: (token: string) => ["public", "batteries", token] as const,
  },
} as const;
