// Exporta o OpenAPI do backend e regenera o cliente TypeScript (src/api/schema.d.ts).
// Usa o Python da venv do backend (Windows ou Linux/macOS); sem venv, tenta "python".
import { execFileSync, execSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const front = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const back = join(front, "..", "backend");
const candidatos = [
  join(back, ".venv", "Scripts", "python.exe"),
  join(back, ".venv", "bin", "python"),
];
const python = candidatos.find((c) => existsSync(c)) ?? "python";

execFileSync(python, ["-m", "app.cli", "openapi", "--saida", join(front, "openapi.json")], {
  cwd: back,
  stdio: "inherit",
});
execSync("npm run gerar-api", { cwd: front, stdio: "inherit" });
