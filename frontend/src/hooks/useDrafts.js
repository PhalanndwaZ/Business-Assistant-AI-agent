import { useEffect, useState } from "react";
import { listDrafts, updateDraft } from "../api/draftsApi.js";

export function useDrafts(conversationId) {
  const [drafts, setDrafts] = useState([]);
  const [error, setError] = useState(null);

  useEffect(function loadConversationDrafts() {
    setDrafts([]);
    setError(null);
    if (!conversationId) return undefined;
    let active = true;
    listDrafts(conversationId).then((items) => {
      if (active) setDrafts(items);
    }).catch((requestError) => {
      if (active) setError(requestError.message);
    });
    return () => { active = false; };
  }, [conversationId]);

  async function save(draftId, patch) {
    const updated = await updateDraft(draftId, patch);
    setDrafts((items) => items.map((draft) => draft.draft_id === draftId ? updated : draft));
    return updated;
  }

  return { drafts, save, error };
}
