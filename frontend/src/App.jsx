import "./styles/tokens.css";
import "./styles/app.css";

import { ChatWindow } from "./components/ChatWindow.jsx";
import { useConversation } from "./hooks/useConversation.js";

/** Render the one-page analyst chat application. */
export default function App() {
  const conversation = useConversation();

  return <ChatWindow {...conversation} />;
}
