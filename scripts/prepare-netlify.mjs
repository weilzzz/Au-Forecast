import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const publishDir = resolve(root, "dist");
const prototypeDir = resolve(root, "prototype");

await mkdir(publishDir, { recursive: true });

for (const file of ["index.html", "app.js", "styles.css", "mock-analysis.json"]) {
  await copyFile(resolve(prototypeDir, file), resolve(publishDir, file));
}

const analysisSource = await readFile(resolve(root, "data", "latest.json"), "utf8");
JSON.parse(analysisSource);
await writeFile(resolve(publishDir, "analysis.json"), analysisSource, "utf8");
await copyFile(resolve(root, "config.json"), resolve(publishDir, "config.json"));
await writeFile(
  resolve(publishDir, "health.json"),
  `${JSON.stringify({ status: "ok", runtime: "netlify" })}\n`,
  "utf8",
);
