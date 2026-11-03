import { useCallback, useEffect, useState } from "react";
import { deleteDocument, listDocuments, uploadDocument } from "../api/documentsApi.js";

const SUPPORTED_TYPES = "PDF, DOCX, TXT, or MD";
const MAX_FILE_SIZE = 10 * 1024 * 1024;
const MAX_DOCUMENTS = 5;

export function useDocuments(userId, conversationId, onConversationCreated) {
  const [documents, setDocuments] = useState([]);
  const [error, setError] = useState(null);

  useEffect(function resetForConversation() {
    setDocuments([]);
    setError(null);
    if (!conversationId) return;
    let active = true;
    listDocuments(conversationId).then((items) => {
      if (active) setDocuments(items);
    }).catch((requestError) => {
      if (active && requestError.status !== 404) setError(requestError.message);
    });
    return () => { active = false; };
  }, [userId, conversationId]);

  const attach = useCallback(async function attachDocument(file) {
    const extension = file.name.includes(".")
      ? file.name.slice(file.name.lastIndexOf(".")).toLowerCase()
      : "";
    if (![".pdf", ".docx", ".txt", ".md"].includes(extension)) {
      const message = "Unsupported file type. Choose a PDF, DOCX, TXT, or MD file.";
      setError(message);
      return null;
    }
    if (file.size > MAX_FILE_SIZE) {
      const message = "The document is larger than the 10 MB limit.";
      setError(message);
      return null;
    }
    const activeCount = documents.filter(
      (document) => document.status !== "failed" && document.document_id && !document.document_id.startsWith("pending-"),
    ).length;
    const pendingCount = documents.filter(
      (document) => document.status === "uploading",
    ).length;
    if (activeCount + pendingCount >= MAX_DOCUMENTS) {
      const message = "A conversation can contain no more than 5 documents.";
      setError(message);
      return null;
    }
    const chip = {
      document_id: `pending-${crypto.randomUUID()}`,
      name: file.name,
      status: "uploading",
      size: file.size,
    };
    setDocuments((items) => [...items, chip]);
    try {
      const uploaded = await uploadDocument(file, conversationId);
      onConversationCreated?.(uploaded.conversation_id);
      setDocuments((items) => items.map((item) => item.document_id === chip.document_id
        ? { ...uploaded, status: "ready", size: file.size }
        : item));
      return uploaded;
    } catch (requestError) {
      const message = requestError.detail || requestError.message;
      setDocuments((items) => items.map((item) => item.document_id === chip.document_id
        ? { ...item, status: "failed", error: message }
        : item));
      setError(message);
      return null;
    }
  }, [conversationId, documents, onConversationCreated]);

  const remove = useCallback(async function removeDocument(documentId) {
    if (documentId.startsWith("pending-")) {
      setDocuments((items) => items.filter((item) => item.document_id !== documentId));
      return;
    }
    if (!conversationId) return;
    await deleteDocument(conversationId, documentId);
    setDocuments((items) => items.filter((item) => item.document_id !== documentId));
  }, [conversationId]);

  return { documents, attach, remove, error, supportedTypes: SUPPORTED_TYPES };
}
