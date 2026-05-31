import { el } from "../../utils/dom.js";
import { renderBmdPlot } from "./bmd_renderer.js";
import { renderDeflectionPlot } from "./deflection_renderer.js";
import { clearLinePlot } from "./plot_utils.js";
import { renderSfdPlot } from "./sfd_renderer.js";

let lastPlots = null;
let resizeBound = false;
let resizeTimer = null;

function validPlotPayload(plots) {
  if (!plots || typeof plots !== "object") return false;
  const x = plots.x;
  return (
    Array.isArray(x) &&
    Array.isArray(plots.shear) &&
    Array.isArray(plots.moment) &&
    Array.isArray(plots.deflection) &&
    x.length === plots.shear.length &&
    x.length === plots.moment.length &&
    x.length === plots.deflection.length &&
    x.length > 1
  );
}

function clearSteelBeamPlots() {
  clearLinePlot("beamCvShear", "beamShearRange");
  clearLinePlot("beamCvMoment", "beamMomentRange");
  clearLinePlot("beamCvDefl", "beamDeflRange");
}

function bindResize() {
  if (resizeBound) return;
  resizeBound = true;
  window.addEventListener("resize", function () {
    if (!lastPlots) return;
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(function () {
      renderSteelBeamPlots(lastPlots);
    }, 120);
  });
}

export function renderSteelBeamPlots(plots) {
  const block = el("beamPlots");
  if (block) block.classList.remove("hidden");

  console.log("[steel-beam-plots] frontend rendering mapping", {
    hasPlots: !!plots,
    xLength: Array.isArray(plots && plots.x) ? plots.x.length : 0,
    shearLength: Array.isArray(plots && plots.shear) ? plots.shear.length : 0,
    momentLength: Array.isArray(plots && plots.moment) ? plots.moment.length : 0,
    deflectionLength: Array.isArray(plots && plots.deflection) ? plots.deflection.length : 0,
    markers: plots && plots.markers,
    meta: plots && plots.meta
  });

  if (!validPlotPayload(plots)) {
    console.warn("[steel-beam-plots] backend plot payload missing required arrays", plots);
    lastPlots = null;
    clearSteelBeamPlots();
    return;
  }

  lastPlots = plots;
  renderSfdPlot(plots);
  renderBmdPlot(plots);
  renderDeflectionPlot(plots);
  bindResize();
}

