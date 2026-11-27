const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const template = fs.readFileSync("templates/index.html", "utf8");

// Test the exact helper used by both subgroup enumeration and card selection.
const helper = template.match(/const subfieldFor = o => o\.subfield \|\| "Geral";/);
assert.ok(helper, "template must define one shared fallback for empty subfields");
assert.ok(template.includes("inField.map(subfieldFor)"),
  "subgroup enumeration must use the shared fallback");
assert.ok(template.includes("subfieldFor(o) === s"),
  "subgroup filtering must use the same shared fallback");

const result = vm.runInNewContext(
  `${helper[0]}; JSON.stringify([
    subfieldFor({ subfield: "Biologia" }),
    subfieldFor({ subfield: "" }),
    subfieldFor({ subfield: null }),
    subfieldFor({})
  ])`
);
assert.equal(result, JSON.stringify(["Biologia", "Geral", "Geral", "Geral"]));

console.log("Frontend subfield grouping tests passed.");
