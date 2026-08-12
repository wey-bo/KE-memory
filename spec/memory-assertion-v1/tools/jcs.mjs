#!/usr/bin/env node

import fs from "node:fs";

function assertUnicodeScalars(value) {
  for (const character of value) {
    const codePoint = character.codePointAt(0);
    if (codePoint >= 0xd800 && codePoint <= 0xdfff) {
      throw new Error("JCS input contains an unpaired Unicode surrogate");
    }
  }
}

function serialize(value) {
  if (value === null) return "null";

  switch (typeof value) {
    case "boolean":
      return value ? "true" : "false";
    case "number": {
      if (!Number.isFinite(value)) {
        throw new Error("JCS input contains a non-finite number");
      }
      return JSON.stringify(value);
    }
    case "string":
      assertUnicodeScalars(value);
      return JSON.stringify(value);
    case "object":
      if (Array.isArray(value)) {
        return `[${value.map(serialize).join(",")}]`;
      }
      return `{${Object.keys(value)
        .sort()
        .map((key) => {
          assertUnicodeScalars(key);
          return `${JSON.stringify(key)}:${serialize(value[key])}`;
        })
        .join(",")}}`;
    default:
      throw new Error(`unsupported JCS value type: ${typeof value}`);
  }
}

try {
  const input = fs.readFileSync(0, "utf8");
  process.stdout.write(serialize(JSON.parse(input)));
} catch (error) {
  process.stderr.write(`JCS_ERROR ${error.message}\n`);
  process.exitCode = 1;
}
