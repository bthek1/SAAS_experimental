import type { LucideIcon } from "lucide-react";
import { BarChart2, ClipboardList, FileStack, Gauge, Layers, Send } from "lucide-react";

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
}

export interface StaticNavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

export const navItems: NavItem[] = [
  { label: "Dashboard", to: "/dashboard", icon: BarChart2 },
  { label: "Questionnaires", to: "/questionnaires", icon: Send },
  { label: "Batteries", to: "/batteries", icon: ClipboardList },
  { label: "Questionnaire types", to: "/questionnaire-types", icon: FileStack },
  { label: "Battery types", to: "/battery-types", icon: Layers },
];

// Files in public/, which the router cannot reach: they need a full page load.
export const staticNavItems: StaticNavItem[] = [
  { label: "Load tests", href: "/loadtest-results.html", icon: Gauge },
];
