import { CaveatList } from "./CaveatList.jsx";
import { FiguresView } from "./FiguresView.jsx";
import { SourceChips } from "./SourceChips.jsx";

/** Display only evidence sections that contain data for this response. */
export function EvidencePanel({ response }) {
  const caveats = Array.isArray(response?.caveats) ? response.caveats : [];
  const sources = Array.isArray(response?.source_metadata)
    ? response.source_metadata
    : Array.isArray(response?.sources)
      ? response.sources
      : [];
  const figures = Array.isArray(response?.figures) ? response.figures : [];
  const evidenceChunks = Array.isArray(response?.evidence_chunks)
    ? response.evidence_chunks.filter(
        (chunk) =>
          chunk !== null &&
          typeof chunk === "object" &&
          typeof chunk.text === "string",
      )
    : [];

  if (
    caveats.length === 0 &&
    sources.length === 0 &&
    figures.length === 0 &&
    evidenceChunks.length === 0
  ) {
    return null;
  }

  return (
    <div className="evidence-panel">
      <header className="evidence-panel__heading">
        <span className="evidence-panel__icon" aria-hidden="true">
          ◈
        </span>
        <div>
          <h3>Evidence explorer</h3>
          <p>
            Click on a figure or citation to inspect the supporting analysis or
            document excerpt.
          </p>
        </div>
      </header>
      {caveats.length > 0 ? <CaveatList caveats={caveats} /> : null}
      {sources.length > 0 ? (
        <SourceChips sources={sources} evidenceChunks={evidenceChunks} />
      ) : null}
      {figures.length > 0 ? <FiguresView figures={figures} /> : null}
    </div>
  );
}
