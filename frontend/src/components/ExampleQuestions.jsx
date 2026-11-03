/** Show suggested questions that can be submitted with one click. */
export function ExampleQuestions({
  questions,
  onSelect,
  disabled = false,
}) {
  /** Give a prompt a short category to make the options easier to scan. */
  function getQuestionCategory(question) {
    const normalized = question.toLowerCase();
    if (normalized.includes("headcount") || normalized.includes("leave")) {
      return "People & policy";
    }
    if (
      normalized.includes("customer") ||
      normalized.includes("product")
    ) {
      return "Customer insights";
    }
    if (normalized.includes("risk") || normalized.includes("unusual")) {
      return "Performance & risk";
    }
    if (
      normalized.includes("revenue") ||
      normalized.includes("sales") ||
      normalized.includes("decline")
    ) {
      return "Revenue insights";
    }
    return "Business insights";
  }

  /** Create a click handler that submits the selected example question. */
  function createQuestionHandler(question) {
    /** Submit this example question to the conversation. */
    function handleQuestionClick() {
      onSelect(question);
    }

    return handleQuestionClick;
  }

  const questionItems = [];
  for (const question of questions) {
    questionItems.push(
      <li key={question}>
        <button
          className="example-question"
          disabled={disabled}
          onClick={createQuestionHandler(question)}
          type="button"
        >
          <span className="example-question__category">
            {getQuestionCategory(question)}
          </span>
          <span className="example-question__text">{question}</span>
          <span className="example-question__arrow" aria-hidden="true">
            →
          </span>
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
