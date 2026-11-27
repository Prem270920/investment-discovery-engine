import { afterEach, describe, expect, it, vi } from "vitest";
import { apiBase, getCarousels } from "./api";

const answerWith = (body) => vi.fn(async () => ({ ok: true, json: async () => body }));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("apiBase", () => {
  it("points at the separate API server on :8000 in development", () => {
    vi.stubEnv("DEV", true);
    expect(apiBase()).toBe("http://localhost:8000");
  });

  it("uses the page's own address in a production build", () => {
    vi.stubEnv("DEV", false);
    expect(apiBase()).toBe("");
  });
});

describe("requests", () => {
  it("call localhost:8000 in development", async () => {
    vi.stubEnv("DEV", true);
    const fetchStub = answerWith({ carousels: [] });
    vi.stubGlobal("fetch", fetchStub);
    await getCarousels();
    expect(fetchStub).toHaveBeenCalledWith("http://localhost:8000/api/carousels");
  });

  it("call a same address path in production, so the API that served the page answers", async () => {
    vi.stubEnv("DEV", false);
    const fetchStub = answerWith({ carousels: [] });
    vi.stubGlobal("fetch", fetchStub);
    await getCarousels("AU");
    expect(fetchStub).toHaveBeenCalledWith("/api/carousels?underlying_market=AU");
  });
});
