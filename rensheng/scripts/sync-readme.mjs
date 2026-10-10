#!/usr/bin/env node

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { repositoryReadmeFromDocs } from "./lib/readme.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourceFile = join(ROOT, "docs/README.md");
const targetFile = join(ROOT, "README.md");
const checkOnly = process.argv.includes("--check");

const expected = repositoryReadmeFromDocs(readFileSync(sourceFile, "utf8"));
const actual = readFileSync(targetFile, "utf8");

if (actual !== expected) {
  if (checkOnly) {
    console.error("README.md: 未与 docs/README.md 同步；运行 npm run sync");
    process.exit(1);
  }
  writeFileSync(targetFile, expected);
  console.log("updated README.md");
} else {
  console.log("README mirror is in sync");
}
