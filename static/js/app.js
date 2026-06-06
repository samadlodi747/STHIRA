// Version-tagged imports so the browser fetches the current controller graph rather than a
// stale cached copy. Bump these (and app.js?v= in index.html) together when controllers change.
import { initSteelBeamController } from "./ui/steel_beam_controller.js?v=11";
import { initSteelColumnController } from "./ui/steel_column_controller.js?v=11";
import { initTimberBeamController } from "./ui/timber_beam_controller.js?v=11";

initSteelColumnController();
initTimberBeamController();
initSteelBeamController();
