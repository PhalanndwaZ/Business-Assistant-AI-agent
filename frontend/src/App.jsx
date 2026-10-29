import "./styles/tokens.css";
import "./styles/app.css";

import { useAuth } from "./auth/useAuth.js";
import { ChatWindow } from "./components/ChatWindow.jsx";
import { LoginView } from "./components/LoginView.jsx";
import { SHOW_DEMO_ACCOUNTS } from "./config.js";
import { useConversation } from "./hooks/useConversation.js";

/** Select the login screen or the authenticated chat workspace. */
export default function App() {
  const auth = useAuth();

  if (auth.isLoading) {
    return (
      <main className="auth-loading" role="status">
        Checking your session...
      </main>
    );
  }
  if (!auth.user) {
    return (
      <LoginView
        onLogin={auth.signIn}
        showDemoAccounts={SHOW_DEMO_ACCOUNTS}
        sessionExpired={auth.sessionExpired}
        hasPendingQuestion={auth.pendingQuestion !== null}
      />
    );
  }

  return (
    <AuthenticatedChat
      key={auth.user.user_id}
      user={auth.user}
      onLogout={auth.signOut}
      pendingQuestion={
        auth.pendingQuestion?.userId === auth.user.user_id
          ? auth.pendingQuestion.question
          : null
      }
      onClearPendingQuestion={auth.clearPendingQuestion}
    />
  );
}

/** Render chat state only while an authenticated user is present. */
function AuthenticatedChat({
  user,
  onLogout,
  pendingQuestion,
  onClearPendingQuestion,
}) {
  const conversation = useConversation(user.user_id);

  return (
    <ChatWindow
      {...conversation}
      user={user}
      onLogout={onLogout}
      pendingQuestion={pendingQuestion}
      onClearPendingQuestion={onClearPendingQuestion}
    />
  );
}
