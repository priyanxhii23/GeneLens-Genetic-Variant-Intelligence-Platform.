import { afterEach, describe, expect, it, vi } from "vitest";
import { api, clearApiCache, qs } from "../lib/api";
import { fmtAF, fmtInt, fmtNum, fmtP, pct } from "../lib/format";
import { wilson } from "../lib/stats";

describe("formatting never turns missing into zero", () => {
  it("renders missing values as a dash", () => {
    expect(fmtAF(null)).toBe("—"); expect(fmtAF(undefined)).toBe("—");
    expect(fmtInt(null)).toBe("—"); expect(fmtP(undefined)).toBe("—"); expect(fmtNum(NaN)).toBe("—"); expect(pct(null)).toBe("—");
  });
  it("keeps a real zero as zero and uses scientific notation for rare AFs", () => {
    expect(fmtAF(0)).toBe("0");
    expect(fmtAF(6.58e-7)).toBe("6.58e-7");
    expect(fmtAF(0.0123)).toBe("0.0123");
    expect(fmtP(0)).toBe("< 1e-300");
  });
});

describe("Wilson interval matches the backend implementation", () => {
  it("gives the published values for 2649/16172", () => {
    const [p, lo, hi] = wilson(2649, 16172)!;
    expect(p).toBeCloseTo(0.16380, 4);
    expect(lo).toBeCloseTo(0.158178, 5);
    expect(hi).toBeCloseTo(0.169585, 5);
  });
  it("is undefined (not zero) for n = 0", () => { expect(wilson(0, 0)).toBeNull(); });
});

describe("query strings", () => {
  it("drops empty values and repeats arrays", () => {
    expect(qs({ a: 1, b: undefined, c: "", d: null, e: ["x", "y"] })).toBe("?a=1&e=x&e=y");
    expect(qs({})).toBe("");
  });
});

describe("request de-duplication and cache", () => {
  afterEach(() => { vi.unstubAllGlobals(); clearApiCache(); });
  it("shares one network request between concurrent identical GETs and reuses it from cache", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify([{ id: "x" }]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const [a, b] = await Promise.all([api.savedComparisons(), api.savedComparisons()]);
    await api.savedComparisons();
    expect(a).toEqual(b);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it("never caches custom-dataset status (it changes while processing)", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await api.customDatasets(); await api.customDatasets();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
  it("turns backend errors into readable messages without stack traces", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "This custom dataset does not exist." }), { status: 404 })));
    await expect(api.customDataset("nope")).rejects.toThrow("This custom dataset does not exist.");
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    await expect(api.customDataset("x")).rejects.toThrow(/Cannot reach the GeneLens backend/);
  });
});
