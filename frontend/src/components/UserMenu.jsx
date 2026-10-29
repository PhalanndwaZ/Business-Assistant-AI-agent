import { RoleBadge } from "./RoleBadge.jsx";

/** Show the current identity and provide a clear sign-out action. */
export function UserMenu({ user, onLogout }) {
  return (
    <div className="user-menu">
      <span className="user-menu__name">{user.name}</span>
      <RoleBadge role={user.role} />
      <button
        className="button button--secondary user-menu__logout"
        onClick={onLogout}
        type="button"
      >
        Log out
      </button>
    </div>
  );
}
