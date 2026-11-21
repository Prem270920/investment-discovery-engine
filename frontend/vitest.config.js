import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config.js";

// Builds on the app's Vite config so tests compile exactly like the app does.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      // The hooks touch window, matchMedia and IntersectionObserver, so tests
      // need a DOM. jsdom has none of the latter two; each test mocks them.
      environment: "jsdom",
      include: ["src/**/*.test.{js,jsx}"],
    },
  }),
);
