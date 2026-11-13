// pytest 가 부르는 보조 스크립트: JSON 입력 목록을 받아 JS 계산 결과를 JSON 으로 출력한다.
// 사용: node tests/sim_node_runner.js <cases.json>
const fs = require("fs");
const path = require("path");
const S = require(path.join(__dirname, "..", "static", "js", "econova-sim.js"));
const cases = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const out = cases.map((c) => {
  if (c.kind === "parse") return S.parseInputs(c.sim, c.raw);
  if (c.kind === "interpret") return S.interpret(c.base, c.now);
  return S.run(c.sim, c.raw);
});
process.stdout.write(JSON.stringify(out));
