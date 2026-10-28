import { EXAMPLE_QUESTIONS } from "../config.js";

/** Show suggested questions that can be submitted with one click. */
export function ExampleQuestions({ onSelect, disabled = false }) {
  /** Create a click handler that submits the selected example question. */
  function createQuestionHandler(question) {
    /** Submit this example question to the conversation. */
    function handleQuestionClick() {
      onSelect(question);
    }

    return handleQuestionClick;
  }

  const questionItems = [];
  for (const question of EXAMPLE_QUESTIONS) {
    questionItems.push(
      <li key={question}>
        <button
          className="example-question"
          disabled={disabled}
          onClick={createQuestionHandler(question)}
          type="button"
        >
          {question}
        </button>
      </li>,
    );
  }

  return (
    <ul className="example-questions" aria-label="Example questions">
      {questionItems}
    </ul>
  );
}
