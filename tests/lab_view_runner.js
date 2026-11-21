// Helper called by pytest: runs the Economics Lab views and returns chart specs plus pixel geometry as JSON.
// Usage: node tests/lab_view_runner.js <cases.json>   (cases.json: {specs, projects, cases: [{sim, raw}]})
const fs = require("fs");
const path = require("path");
const M = require(path.join(__dirname, "..", "public", "static", "js", "econova-lab-models.js"));
const U = require(path.join(__dirname, "..", "public", "static", "js", "econova-lab-ui.js"));
const data = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const out = data.cases.map((c) => {
  const run = M.run(c.sim, data.specs[c.sim], c.raw, data.projects);
  const view = U.views[c.sim](run.inputs, run.results, null, data.projects);
  return { results: run.results, summary: view.summary, notes: view.notes, extra: view.extra || "",
           charts: view.charts.map((ch) => ({ spec: ch, geometry: U.geometry(ch) })) };
});
process.stdout.write(JSON.stringify({ out, frame: { W: U.W, H: U.H, PL: U.PL, PR: U.PR, PT: U.PT, PB: U.PB } }));
