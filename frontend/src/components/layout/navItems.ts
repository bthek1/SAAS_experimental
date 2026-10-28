import type { LucideIcon } from "lucide-react";
import { BarChart2, ClipboardList, FileStack, Layers, Send } from "lucide-react";

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
}

export const navItems: NavItem[] = [
  { label: "Dashboard", to: "/demo/chart", icon: BarChart2 },
  { label: "Questionnaires", to: "/questionnaires", icon: Send },
  { label: "Batteries", to: "/batteries", icon: ClipboardList },
  { label: "Questionnaire types", to: "/questionnaire-types", icon: FileStack },
  { label: "Battery types", to: "/battery-types", icon: Layers },
];
