import ReactMarkdown from "react-markdown";

/** Render a markdown link as an explicit, safely isolated user-click target. */
function renderLink({ href, children }) {
  if (!href) {
    return <span>{children}</span>;
  }

  return (
    <a href={href} rel="noopener noreferrer" target="_blank">
      {children}
    </a>
  );
}

/** Show image alt text without fetching remote image content from an answer. */
function renderImageAsText({ alt }) {
  return <span>{alt || ""}</span>;
}

const MARKDOWN_COMPONENTS = {
  a: renderLink,
  img: renderImageAsText,
};

/** Render untrusted answer markdown without enabling raw HTML. */
export function AnswerText({ content }) {
  return (
    <div className="answer-text">
      <ReactMarkdown
        components={MARKDOWN_COMPONENTS}
        skipHtml={false}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
