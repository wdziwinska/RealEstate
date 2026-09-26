#!/usr/bin/env node

import { pathToFileURL } from "node:url";

console.log = (...args) => console.error(...args);
console.info = (...args) => console.error(...args);
console.debug = (...args) => console.error(...args);
console.warn = (...args) => console.error(...args);

const targetScript = process.argv[2] || process.env.MCP_WEB_SEARCH_REAL_SCRIPT;

if (!targetScript) {
  console.error("MCP_WEB_SEARCH_REAL_SCRIPT is not configured.");
  process.exit(1);
}

await import(pathToFileURL(targetScript).href);
