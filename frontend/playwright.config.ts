import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const frontendDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(frontendDir, "..");
const python = process.env.E2E_PYTHON ?? (
  process.platform === "win32" ? ".\\.venv\\Scripts\\python.exe" : "python"
);
const databaseUrl = process.env.E2E_DATABASE_URL
  ?? "postgresql+psycopg://commerce:commerce@127.0.0.1:5432/commerce_pilot_e2e";

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI
    ? [["line"], ["html", { open: "never" }]]
    : [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:15173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: python + " -m uvicorn app.main:app --host 127.0.0.1 --port 18000",
      cwd: projectRoot,
      url: "http://127.0.0.1:18000/api/v1/health",
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        APP_ENV: "development",
        LLM_PROVIDER: "deterministic",
        RAG_PROVIDER: "deterministic",
        DATABASE_URL: databaseUrl,
        JWT_SECRET_KEY: process.env.JWT_SECRET_KEY
          ?? "e2e-only-secret-key-at-least-thirty-two-bytes",
      } as Record<string, string>,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 15173",
      cwd: frontendDir,
      url: "http://127.0.0.1:15173",
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        VITE_API_PROXY_TARGET: "http://127.0.0.1:18000",
      } as Record<string, string>,
    },
  ],
});
