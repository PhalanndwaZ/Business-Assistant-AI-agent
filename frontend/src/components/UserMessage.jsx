/** Render the user's question as plain, safely escaped text. */
export function UserMessage({ content }) {
  return (
    <article className="message-bubble message-bubble--user">
      <p>{content}</p>
    </article>
  );
}
