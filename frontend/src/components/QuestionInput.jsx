import { useState } from "react";

import { QUESTION_LENGTH_LIMIT } from "../config.js";
import { DocumentPanel } from "./DocumentPanel.jsx";

/** Render an accessible question box with Enter and Shift+Enter behavior. */
export function QuestionInput({
  disabled,
  inputRef,
  onSend,
  documents = [],
  onAttachDocument,
  onRemoveDocument,
  documentError,
}) {
  const [value, setValue] = useState("");
  const showCharacterCount =
    value.length >= QUESTION_LENGTH_LIMIT - 100;
  const describedBy = showCharacterCount
    ? "question-input-help question-input-count"
    : "question-input-help";

  /** Update the draft as the user types. */
  function handleChange(event) {
    setValue(event.target.value);
    event.target.style.height = "auto";
    event.target.style.height = `${Math.min(event.target.scrollHeight, 128)}px`;
    event.target.style.overflowY =
      event.target.scrollHeight > 128 ? "auto" : "hidden";
  }

  /** Submit on Enter while preserving a newline for Shift+Enter. */
  function handleKeyDown(event) {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      handleSubmit(event);
    }
  }

  /** Trim and submit a non-empty question, then clear the draft. */
  function handleSubmit(event) {
    event.preventDefault();
    const question = value.trim();
    if (!question || disabled) {
      return;
    }
    onSend(question);
    setValue("");
    if (inputRef && "current" in inputRef && inputRef.current) {
      inputRef.current.style.height = "";
      inputRef.current.style.overflowY = "";
    }
  }

  return (
    <form className="question-form" onSubmit={handleSubmit}>
      <div className="question-form__heading">
        <span className="question-form__heading-mark" aria-hidden="true">
          ✦
        </span>
        <span>Ask a question</span>
        <span className="question-form__heading-hint">
          About your business data
        </span>
      </div>
      <label className="visually-hidden" htmlFor="question-input">
        Ask a business question
      </label>
      <div className="question-form__row">
        <textarea
          autoComplete="off"
          aria-describedby={describedBy}
          id="question-input"
          disabled={disabled}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="Ask about revenue, customers, or trends..."
          ref={inputRef}
          rows={1}
          value={value}
        />
        <button
          className="button button--primary"
          disabled={disabled || !value.trim()}
          type="submit"
        >
          Send
        </button>
      </div>
      <div className="question-form__footer">
        {onAttachDocument ? (
          <DocumentPanel
            disabled={disabled}
            documents={documents}
            error={documentError}
            onAttach={onAttachDocument}
            onRemove={onRemoveDocument}
          />
        ) : null}
        <div className="question-form__meta">
          <span id="question-input-help">
            Enter to send · Shift+Enter for a new line
          </span>
          {showCharacterCount ? (
            <span
              id="question-input-count"
              className={
                value.length > QUESTION_LENGTH_LIMIT
                  ? "question-form__count question-form__count--over"
                  : "question-form__count"
              }
            >
              <span className="visually-hidden">Question length: </span>
              {value.length}/{QUESTION_LENGTH_LIMIT}
            </span>
          ) : null}
        </div>
      </div>
    </form>
  );
}
