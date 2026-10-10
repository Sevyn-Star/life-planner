#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const candidates = [
  process.env.PDF_PYTHON,
  join(homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"),
  "python3",
].filter(Boolean);

let python;
for (const candidate of candidates) {
  if (candidate.includes("/") && !existsSync(candidate)) continue;
  const probe = spawnSync(candidate, ["-c", "import reportlab, pypdf, PIL"], {
    cwd: ROOT,
    encoding: "utf8",
  });
  if (probe.status === 0) {
    python = candidate;
    break;
  }
}

if (!python) {
  console.error("PDF 依赖不可用；请运行 python3 -m pip install -r requirements-pdf.txt");
  process.exit(1);
}

const result = spawnSync(python, [join(ROOT, "scripts/build-pdf.py"), ...process.argv.slice(2)], {
  cwd: ROOT,
  encoding: "utf8",
  env: {
    ...process.env,
    PYTHONHASHSEED: "0",
    SOURCE_DATE_EPOCH: "946684800",
    TZ: "UTC",
  },
  stdio: "inherit",
});
process.exit(result.status ?? 1);
