import { renderLinePlot } from "./plot_utils.js";

export function renderSfdPlot(plots) {
  renderLinePlot({
    canvasId: "beamCvShear",
    rangeId: "beamShearRange",
    x: plots && plots.x,
    y: plots && plots.shear,
    marker: plots && plots.markers && plots.markers.max_shear,
    xLabel: "x (m)",
    yLabel: "V (kN)",
    tooltipName: "V",
    unit: (plots && plots.meta && plots.meta.shear_unit) || "kN",
    digits: 3,
    color: "rgba(89,196,255,0.96)",
    fillColor: "rgba(89,196,255,0.11)",
    markerColor: "rgba(255,209,102,0.96)"
  });
}

