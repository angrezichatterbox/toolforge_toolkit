"use strict";

/**
 * Postinstall script: verifies Python 3 is available and prints setup info.
 * Does NOT exit with error — just warns, so the install itself doesn't fail.
 */

const { execFileSync } = require("child_process");

function findPython() {
  for (const candidate of ["python3", "python"]) {
    try {
      const v = execFileSync(candidate, ["--version"], {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
      }).trim();
      if (v.startsWith("Python 3")) return { cmd: candidate, version: v };
    } catch (_) {}
  }
  return null;
}

const python = findPython();

console.log("\n┌─────────────────────────────────────────────┐");
console.log("│         deployr — Toolforge CLI             │");
console.log("└─────────────────────────────────────────────┘");

if (!python) {
  console.warn(
    "\n⚠  Python 3 was not detected on your PATH.\n" +
      "   Deployr requires Python 3.9+.\n" +
      "   Install from https://python.org and re-run: npm install -g deployr-cli\n"
  );
} else {
  console.log(`\n✔  Found ${python.version} at '${python.cmd}'`);
  console.log("✔  You can now run: deployr\n");
  console.log("   Run 'deployr --help' to see all available commands.");
}

console.log("");
