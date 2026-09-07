import type { Role } from "./api/types";

/** Display names for the API's roles and content labels; unknown ones fall through. */
const ROLE_NAMES: Record<string, string> = {
  employee: "Employee",
  manager: "Manager",
  hr: "People & Culture",
  finance: "Finance",
  leadership: "Leadership",
};

const LABEL_NAMES: Record<string, string> = {
  all: "All staff",
  managers: "Managers",
  hr: "People & Culture",
  finance: "Finance",
  leadership: "Leadership",
};

/** Demo personas from the corpus fact sheet (corpus/FACTS.md) — shown in the switcher. */
export const PERSONAS: Record<string, string> = {
  employee: "Anna, backend engineer",
  manager: "Ines, engineering manager",
  hr: "Lea, people operations",
  finance: "Tomasz, CFO",
  leadership: "Marta, CEO",
};

export const roleName = (role: string) => ROLE_NAMES[role] ?? role;
export const labelName = (label: string) => LABEL_NAMES[label] ?? label;

/** A role unlocks a question when it can read every label the question's min_role can. */
export function unlocks(roles: Role[], current: string, minRole: string): boolean {
  const mine = roles.find((r) => r.role === current)?.labels;
  const needed = roles.find((r) => r.role === minRole)?.labels;
  if (!mine || !needed) return current === minRole;
  return needed.every((label) => mine.includes(label));
}

/** The least-privileged role (API order) that can read each label, deduplicated. */
export function unlockingRoles(roles: Role[], labels: string[]): string[] {
  const out: string[] = [];
  for (const label of labels) {
    const role = roles.find((r) => r.labels.includes(label));
    if (role && !out.includes(role.role)) out.push(role.role);
  }
  return out;
}

/** "A", "A and B", "A, B and C" */
export function joinNames(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/** A role may read a whole document only when it can read every label the document holds. */
export function canRead(roles: Role[], current: string, labels: string[]): boolean {
  if (!labels.length) return true;
  const mine = roles.find((r) => r.role === current)?.labels;
  if (!mine) return false;
  return labels.every((label) => mine.includes(label));
}
