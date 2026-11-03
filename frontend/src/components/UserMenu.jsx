import { RoleBadge } from "./RoleBadge.jsx";

/** Show the current identity and provide a clear sign-out action. */
export function UserMenu({ user, onLogout }) {
  const initials = (user.name || "User")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();

  return (
    <div className="user-menu" aria-label="Account">
      <div className="user-menu__profile">
        <span className="user-menu__avatar" aria-hidden="true">
          {initials}
        </span>
        <span className="user-menu__identity">
          <span className="user-menu__name">{user.name}</span>
          <span className="user-menu__username">{user.username}</span>
        </span>
      </div>
      <div className="user-menu__actions">
        <RoleBadge role={user.role} />
        <button
          aria-label="Log out"
          className="user-menu__logout"
          onClick={onLogout}
          title="Log out"
          type="button"
        >
          <svg
            aria-hidden="true"
            className="user-menu__logout-icon"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.7"
            viewBox="0 0 24 24"
          >
            <path d="M10 17l5-5-5-5M15 12H3" />
            <path d="M12 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6" />
          </svg>
          <span className="user-menu__logout-label">Log out</span>
        </button>
      </div>
    </div>
  );
}
