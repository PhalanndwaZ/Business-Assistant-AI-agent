import { AnswerText } from "./AnswerText.jsx";
import { EvidencePanel } from "./EvidencePanel.jsx";
import {
  getReportFilename,
  removeReportPathFromAnswer,
  ReportNotice,
} from "./ReportNotice.jsx";

/** Render an assistant answer followed by its current-turn evidence. */
export function AssistantMessage({ content, response }) {
  const reportFilename = getReportFilename(
    content,
    response?.report_filename,
  );
  const visibleAnswer = removeReportPathFromAnswer(
    content,
    response?.report_filename,
  );

  return (
    <article className="message-bubble message-bubble--assistant">
      <AnswerText content={visibleAnswer} />
      <ReportNotice
        answer={content}
        reportFilename={reportFilename}
      />
      <EvidencePanel response={response} />
    </article>
  );
}
