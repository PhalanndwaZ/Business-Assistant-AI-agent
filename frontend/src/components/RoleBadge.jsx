const ROLE_LABELS = {
  sales: "Sales",
  hr: "HR",
  manager: "Manager",
  admin: "Admin",
};

/** Display the authenticated user's role as a compact, labelled badge. */
export function RoleBadge({ role }) {
  const label = ROLE_LABELS[role] || "User";
  return (
    <span className={`role-badge role-badge--${role}`} aria-label={`Role: ${label}`}>
      {label}
    </span>
  );
}
