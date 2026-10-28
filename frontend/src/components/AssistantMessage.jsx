import { AnswerText } from "./AnswerText.jsx";
import { EvidencePanel } from "./EvidencePanel.jsx";
import { ReportNotice } from "./ReportNotice.jsx";

/** Render an assistant answer followed by its current-turn evidence. */
export function AssistantMessage({ content, response }) {
  return (
    <article className="message-bubble message-bubble--assistant">
      <AnswerText content={content} />
      <ReportNotice
        answer={content}
        reportFilename={response?.report_filename}
      />
      <EvidencePanel response={response} />
    </article>
  );
}
