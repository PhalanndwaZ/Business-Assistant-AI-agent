import { CaveatList } from "./CaveatList.jsx";
import { FiguresView } from "./FiguresView.jsx";
import { SourceChips } from "./SourceChips.jsx";

/** Display only evidence sections that contain data for this response. */
export function EvidencePanel({ response }) {
  const caveats = Array.isArray(response?.caveats) ? response.caveats : [];
  const sources = Array.isArray(response?.sources) ? response.sources : [];
  const figures = Array.isArray(response?.figures) ? response.figures : [];

  if (caveats.length === 0 && sources.length === 0 && figures.length === 0) {
    return null;
  }

  return (
    <div className="evidence-panel">
      {caveats.length > 0 ? <CaveatList caveats={caveats} /> : null}
      {sources.length > 0 ? <SourceChips sources={sources} /> : null}
      {figures.length > 0 ? <FiguresView figures={figures} /> : null}
    </div>
  );
}
