#!/usr/bin/env node

import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const separator = process.argv.indexOf("--");
if (separator < 0 || separator === process.argv.length - 1) {
  throw new Error("livespec ACP context proxy requires an adapter command after --");
}

const loads = JSON.parse(process.env.LIVESPEC_ACP_CONTEXT_LOADS ?? "{}");
const root = process.env.LIVESPEC_ACP_CONTEXT_ROOT ?? process.cwd();
const instructionText = (loads.instruction_files ?? [])
  .map((path) => readFileSync(resolve(root, path), "utf8"))
  .join("\n\n");
const adapter = process.argv.slice(separator + 1);
const adapterEnv = { ...process.env };
while (adapter.length > 1 && /^[A-Za-z_][A-Za-z0-9_]*=/.test(adapter[0])) {
  const assignment = adapter.shift();
  const equals = assignment.indexOf("=");
  adapterEnv[assignment.slice(0, equals)] = assignment.slice(equals + 1);
}
const child = spawn(adapter[0], adapter.slice(1), {
  env: adapterEnv,
  stdio: ["pipe", "pipe", "inherit"],
});

process.stdin.setEncoding("utf8");
let pending = "";
process.stdin.on("data", (chunk) => {
  pending += chunk;
  const lines = pending.split("\n");
  pending = lines.pop() ?? "";
  for (const line of lines) {
    if (line === "") continue;
    const message = JSON.parse(line);
    if (message.method === "session/new") {
      message.params ??= {};
      message.params.mcpServers = {};
      message.params._meta ??= {};
      message.params._meta.claudeCode ??= {};
      message.params._meta.claudeCode.options = {
        ...(message.params._meta.claudeCode.options ?? {}),
        settingSources: [],
        strictMcpConfig: true,
        systemPrompt: { type: "preset", preset: "claude_code", append: instructionText },
      };
    }
    child.stdin.write(`${JSON.stringify(message)}\n`);
  }
});
process.stdin.on("end", () => {
  if (pending !== "") child.stdin.write(`${pending}\n`);
  child.stdin.end();
});
child.stdout.pipe(process.stdout);
child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 1);
});
