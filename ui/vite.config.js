import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

// In dev, every request for /data.json re-runs `python -m goodman export` (at most
// once every 3 s), so new attempt/claims/result files show up without a restart.
function liveExport() {
  const root = resolve(__dirname, "..");
  const venv = resolve(root, ".venv/bin/python");
  const python = existsSync(venv) ? venv : "python3";
  let last = 0;
  return {
    name: "goodman-live-export",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (req.url && req.url.startsWith("/data.json") && Date.now() - last > 3000) {
          last = Date.now();
          try {
            execFileSync(python, ["-m", "goodman", "export"], { cwd: root, stdio: "ignore", timeout: 20000 });
          } catch (e) {
            server.config.logger.warn(`goodman export failed: ${e.message}`);
          }
        }
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), liveExport()],
  server: { host: "127.0.0.1" },
  build: { chunkSizeWarningLimit: 1200 },
});
