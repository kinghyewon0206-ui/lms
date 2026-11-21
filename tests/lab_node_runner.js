// Helper called by pytest: runs Economics Lab models 3-9 in JavaScript and prints the results as JSON.
// Usage: node tests/lab_node_runner.js <cases.json>   (cases.json: {specs, projects, cases: [{sim, raw}]})
const fs = require("fs");
const path = require("path");
const L = require(path.join(__dirname, "..", "public", "static", "js", "econova-lab-models.js"));
const data = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const out = data.cases.map((c) => L.run(c.sim, data.specs[c.sim], c.raw, data.projects));
process.stdout.write(JSON.stringify(out));
