import { defineConfig } from "vitest/config";
export default defineConfig({ test: { environment: "node", include: ["tests-ts/**/*.test.ts"], exclude: ["tests-ts/**/*.integration.test.ts"] }, resolve: { alias: { "@": new URL("./src", import.meta.url).pathname } } });
