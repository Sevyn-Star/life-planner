import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const read = (source) => readFileSync(resolve("docs", source), "utf8");

test("collaboration diagnostics stay aligned across languages and entry points", () => {
  const pages = [
    ["threads/part-1/0-cefr.md", ["转述与调解", "在线互动", "误解修复"]],
    ["templates/english-diagnostic.md", ["转述与调解", "在线互动", "误解修复"]],
    ["en/threads/part-1/0-cefr.md", ["Mediation and retelling", "Online interaction", "Repairing misunderstanding"]],
    ["en/templates/english-diagnostic.md", ["Mediation and retelling", "Online interaction", "Repairing misunderstanding"]],
  ];
  for (const [source, terms] of pages) {
    const content = read(source);
    for (const term of terms) assert.match(content, new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")), `${source} is missing ${term}`);
  }
});
