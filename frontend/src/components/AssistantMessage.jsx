import { AnswerText } from "./AnswerText.jsx";
import { ChartGrid } from "./ChartGrid.jsx";
import { EvidencePanel } from "./EvidencePanel.jsx";
import {
  getReportFilename,
  removeReportPathFromAnswer,
  ReportNotice,
} from "./ReportNotice.jsx";
import {
  getRedactionNotice,
  ModerationNotice,
} from "./ModerationNotice.jsx";

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
  const isRefused = response?.moderation?.status === "refused";
  const redactionNotice = getRedactionNotice(response?.moderation);
  const answerRepeatsNotice =
    redactionNotice &&
    typeof visibleAnswer === "string" &&
    visibleAnswer.trim() === redactionNotice.trim();
  const evidenceResponse =
    redactionNotice && Array.isArray(response?.caveats)
      ? {
          ...response,
          caveats: response.caveats.filter(
            (caveat) =>
              typeof caveat !== "string" ||
              caveat.trim() !== redactionNotice.trim(),
          ),
        }
      : response;

  return (
    <article
      className={
        isRefused
          ? "message-bubble message-bubble--assistant message-bubble--assistant-refused"
          : "message-bubble message-bubble--assistant"
      }
    >
      {answerRepeatsNotice ? null : <AnswerText content={visibleAnswer} />}
      <ModerationNotice moderation={response?.moderation} />
      <ChartGrid charts={response?.charts} />
      <ReportNotice
        answer={content}
        reportFilename={reportFilename}
      />
      <EvidencePanel response={evidenceResponse} />
    </article>
  );
}
