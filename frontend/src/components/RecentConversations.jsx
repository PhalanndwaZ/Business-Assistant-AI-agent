import { UserMenu } from "./UserMenu.jsx";

/** Render the bounded local chat history as a selectable sidebar or drawer. */
export function RecentConversations({
  conversations,
  activeConversationId,
  disabled,
  isOpen,
  isCollapsed,
  darkMode,
  sidebarRef,
  headingRef,
  user,
  onSelect,
  onNewConversation,
  onToggleCollapsed,
  onToggleDarkMode,
  onFocusWorkspace,
  onLogout,
  onClose,
  onKeyDown,
}) {
  const groupedItems = new Map();
  for (const conversation of conversations) {
    const group = getConversationGroup(conversation.updatedAt);
    const isActive = conversation.conversationId === activeConversationId;
    const items = groupedItems.get(group) || [];
    items.push(
      <li key={conversation.conversationId}>
        <button
          aria-current={isActive ? "page" : undefined}
          className={
            isActive
              ? "recent-chat-button recent-chat-button--active"
              : "recent-chat-button"
          }
          aria-label={`Open chat: ${conversation.title}`}
          disabled={disabled}
          onClick={() => onSelect(conversation.conversationId)}
          title={conversation.title}
          type="button"
        >
          <span>{conversation.title}</span>
        </button>
      </li>,
    );
    groupedItems.set(group, items);
  }

  return (
    <>
      <aside
        aria-label="Recent conversations"
        aria-modal={isOpen ? "true" : undefined}
        className={
          [
            "recent-sidebar",
            isOpen ? "recent-sidebar--open" : "",
            isCollapsed ? "recent-sidebar--collapsed" : "",
          ]
            .filter(Boolean)
            .join(" ")
        }
        id="recent-conversations"
        onKeyDown={onKeyDown}
        ref={sidebarRef}
        role={isOpen ? "dialog" : undefined}
      >
        <div className="recent-sidebar__top">
          <div className="recent-sidebar__brand">
            <a
              aria-label="Business Analyst AI home"
              className="recent-sidebar__brand-name"
              href="/"
            >
              <span className="recent-sidebar__brand-mark" aria-hidden="true">
                BA
              </span>
              <span className="recent-sidebar__brand-label">
                Business Analyst AI
              </span>
            </a>
            <button
              aria-controls="recent-conversations"
              aria-expanded={!isCollapsed}
              aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              className="recent-sidebar__collapse"
              onClick={onToggleCollapsed}
              title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              type="button"
            >
              <SidebarIcon name="collapse" />
            </button>
          </div>
          <button
            aria-label="Close chat history"
            className="recent-sidebar__close"
            onClick={onClose}
            type="button"
          >
            <SidebarIcon name="close" />
          </button>
        </div>
        <nav aria-label="Workspace navigation" className="sidebar-navigation">
          <button
            aria-current="page"
            className="sidebar-navigation__item sidebar-navigation__item--active"
            onClick={onFocusWorkspace}
            title="Workspace"
            type="button"
          >
            <SidebarIcon name="workspace" />
            <span className="sidebar-navigation__label">Workspace</span>
          </button>
          <button
            aria-pressed={darkMode}
            className="sidebar-navigation__item"
            onClick={onToggleDarkMode}
            title={darkMode ? "Switch to light mode" : "Switch to dark mode"}
            type="button"
          >
            <SidebarIcon name={darkMode ? "sun" : "moon"} />
            <span className="sidebar-navigation__label">
              {darkMode ? "Light mode" : "Dark mode"}
            </span>
          </button>
          <button
            className="sidebar-navigation__item sidebar-navigation__item--new"
            disabled={disabled}
            onClick={onNewConversation}
            title="New chat"
            type="button"
          >
            <SidebarIcon name="new-chat" />
            <span className="sidebar-navigation__label">New chat</span>
          </button>
        </nav>
        <section
          aria-label="Saved conversations"
          className="recent-sidebar__history"
        >
          <div className="recent-sidebar__header">
            <h2 ref={headingRef} tabIndex={-1}>
              Recent chats
            </h2>
          </div>
          {groupedItems.size > 0 ? (
            <nav aria-label="Recent conversations">
              <div className="recent-chat-groups">
                {[...groupedItems].map(([group, items]) => (
                  <section className="recent-chat-group" key={group}>
                    <h3>{group}</h3>
                    <ul className="recent-chat-list">{items}</ul>
                  </section>
                ))}
              </div>
            </nav>
          ) : (
            <p className="recent-sidebar__empty">
              Your chats will appear here.
            </p>
          )}
        </section>
        <div className="recent-sidebar__account">
          <UserMenu user={user} onLogout={onLogout} />
        </div>
      </aside>
      {isOpen ? (
        <button
          aria-label="Close recent conversations"
          className="recent-sidebar-backdrop"
          onClick={onClose}
          tabIndex={-1}
          type="button"
        />
      ) : null}
    </>
  );
}

function SidebarIcon({ name }) {
  const commonProps = {
    "aria-hidden": true,
    className: "sidebar-icon",
    fill: "none",
    stroke: "currentColor",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    strokeWidth: 1.7,
    viewBox: "0 0 24 24",
  };

  if (name === "workspace") {
    return (
      <svg {...commonProps}>
        <rect height="7" rx="1.5" width="7" x="4" y="4" />
        <rect height="7" rx="1.5" width="7" x="13" y="4" />
        <rect height="7" rx="1.5" width="7" x="4" y="13" />
        <rect height="7" rx="1.5" width="7" x="13" y="13" />
      </svg>
    );
  }
  if (name === "new-chat") {
    return (
      <svg {...commonProps}>
        <path d="M12 5v14M5 12h14" />
      </svg>
    );
  }
  if (name === "collapse") {
    return (
      <svg {...commonProps}>
        <path d="M15 5l-7 7 7 7" />
      </svg>
    );
  }
  if (name === "close") {
    return (
      <svg {...commonProps}>
        <path d="M18 6L6 18M6 6l12 12" />
      </svg>
    );
  }
  if (name === "moon") {
    return (
      <svg {...commonProps}>
        <path d="M20.2 15.1A8.3 8.3 0 0 1 8.9 3.8 8.5 8.5 0 1 0 20.2 15.1Z" />
      </svg>
    );
  }
  if (name === "sun") {
    return (
      <svg {...commonProps}>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" />
      </svg>
    );
  }
  return null;
}

/** Place a saved chat in a familiar relative-date history section. */
function getConversationGroup(updatedAt) {
  const conversationDate = new Date(updatedAt);
  if (Number.isNaN(conversationDate.getTime())) {
    return "Older";
  }

  const today = new Date();
  const todayUtc = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  const conversationUtc = Date.UTC(
    conversationDate.getFullYear(),
    conversationDate.getMonth(),
    conversationDate.getDate(),
  );
  const daysAgo = Math.floor((todayUtc - conversationUtc) / 86_400_000);

  if (daysAgo <= 0) {
    return "Today";
  }
  if (daysAgo === 1) {
    return "Yesterday";
  }
  if (daysAgo <= 7) {
    return "Previous 7 days";
  }
  return "Older";
}
