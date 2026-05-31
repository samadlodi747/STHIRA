import { renderLinePlot } from "./plot_utils.js";

export function renderBmdPlot(plots) {
  renderLinePlot({
    canvasId: "beamCvMoment",
    rangeId: "beamMomentRange",
    x: plots && plots.x,
    y: plots && plots.moment,
    marker: plots && plots.markers && plots.markers.max_moment,
    xLabel: "x (m)",
    yLabel: "M (kNm)",
    tooltipName: "M",
    unit: (plots && plots.meta && plots.meta.moment_unit) || "kNm",
    digits: 3,
    color: "rgba(255,209,102,0.96)",
    fillColor: "rgba(255,209,102,0.12)",
    markerColor: "rgba(138,240,178,0.96)"
  });
}

