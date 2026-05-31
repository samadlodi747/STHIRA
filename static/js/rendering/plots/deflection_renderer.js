import { renderLinePlot } from "./plot_utils.js";

export function renderDeflectionPlot(plots) {
  renderLinePlot({
    canvasId: "beamCvDefl",
    rangeId: "beamDeflRange",
    x: plots && plots.x,
    y: plots && plots.deflection,
    marker: plots && plots.markers && plots.markers.max_deflection,
    xLabel: "x (m)",
    yLabel: "delta (mm)",
    tooltipName: "delta",
    unit: (plots && plots.meta && plots.meta.deflection_unit) || "mm",
    digits: 2,
    color: "rgba(138,240,178,0.96)",
    fillColor: "rgba(138,240,178,0.10)",
    markerColor: "rgba(255,209,102,0.96)"
  });
}

