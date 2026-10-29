import { RankingBarsView } from "../components/charts/RankingBarsView.jsx";
import { LineView } from "../components/charts/LineView.jsx";
import { CompareBarsView } from "../components/charts/CompareBarsView.jsx";
import { WaterfallView } from "../components/charts/WaterfallView.jsx";
import { BandLineView } from "../components/charts/BandLineView.jsx";
import { SideBySidePairView } from "../components/charts/SideBySidePairView.jsx";

export const chartRenderers = new Map();
chartRenderers.set("ranking_bars", RankingBarsView);
chartRenderers.set("line", LineView);
chartRenderers.set("compare_bars", CompareBarsView);
chartRenderers.set("waterfall", WaterfallView);
chartRenderers.set("line_with_expected_range", BandLineView);
chartRenderers.set("side_by_side_pair", SideBySidePairView);

/** Return a renderer only for chart types implemented by the frontend. */
export function getChartRenderer(type) {
  return typeof type === "string" ? chartRenderers.get(type) || null : null;
}
