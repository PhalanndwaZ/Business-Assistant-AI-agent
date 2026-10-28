/** Render the bounded local chat history as a selectable sidebar or drawer. */
export function RecentConversations({
  conversations,
  activeConversationId,
  disabled,
  isOpen,
  sidebarRef,
  headingRef,
  onSelect,
  onNewConversation,
  onClose,
  onKeyDown,
}) {
  const items = [];
  for (const conversation of conversations) {
    const isActive = conversation.conversationId === activeConversationId;
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
  }

  return (
    <>
      <aside
        aria-label="Recent conversations"
        aria-modal={isOpen ? "true" : undefined}
        className={
          isOpen
            ? "recent-sidebar recent-sidebar--open"
            : "recent-sidebar"
        }
        id="recent-conversations"
        onKeyDown={onKeyDown}
        ref={sidebarRef}
        role={isOpen ? "dialog" : undefined}
      >
        <div className="recent-sidebar__brand">
          <a
            aria-label="Business Analyst AI home"
            className="recent-sidebar__brand-name"
            href="/"
          >
            <span className="recent-sidebar__brand-mark" aria-hidden="true">
              BA
            </span>
            <span>Business Analyst AI</span>
          </a>
          <button
            className="button button--secondary recent-sidebar__close"
            onClick={onClose}
            type="button"
          >
            Close
          </button>
        </div>
        <button
          className="button button--new-chat"
          onClick={onNewConversation}
          type="button"
        >
          <span aria-hidden="true">+</span>
          New chat
        </button>
        <div className="recent-sidebar__header">
          <h2 ref={headingRef} tabIndex={-1}>
            Chats
          </h2>
        </div>
        <nav aria-label="Saved conversations">
          {items.length > 0 ? (
            <ul className="recent-chat-list">{items}</ul>
          ) : (
            <p className="recent-sidebar__empty">
              Your chats will appear here.
            </p>
          )}
        </nav>
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
