/** Holds the currently selected analysis so every module works on the same dataset. */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import type { AnalysisDetail } from "./types";

interface Ctx {
  analysisId: string | null;
  detail: AnalysisDetail | null;
  loading: boolean;
  error: string | null;
  select: (id: string | null) => void;
  refresh: () => Promise<void>;
}
const AnalysisCtx = createContext<Ctx>({} as Ctx);
const KEY = "genelens-analysis";

export function AnalysisProvider({ children }: { children: ReactNode }) {
  const [analysisId, setId] = useState<string | null>(() => { try { return localStorage.getItem(KEY); } catch { return null; } });
  const [detail, setDetail] = useState<AnalysisDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (id: string | null) => {
    if (!id) { setDetail(null); return; }
    setLoading(true); setError(null);
    try { setDetail(await api.analysis(id)); }
    catch (e) {
      setError((e as Error).message); setDetail(null);
      if ((e as { status?: number }).status === 404) { setId(null); try { localStorage.removeItem(KEY); } catch { /* */ } }
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(analysisId); }, [analysisId, load]);

  const select = useCallback((id: string | null) => {
    setId(id);
    try { if (id) localStorage.setItem(KEY, id); else localStorage.removeItem(KEY); } catch { /* */ }
  }, []);

  return (
    <AnalysisCtx.Provider value={{ analysisId, detail, loading, error, select, refresh: () => load(analysisId) }}>
      {children}
    </AnalysisCtx.Provider>
  );
}
export const useAnalysis = () => useContext(AnalysisCtx);

/** Small data-fetching hook with loading/error state. */
export function useFetch<T>(fn: (() => Promise<T>) | null, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!fn) { setData(null); return; }
    let alive = true;
    setLoading(true); setError(null);
    fn().then((d) => alive && setData(d)).catch((e) => alive && setError((e as Error).message)).finally(() => alive && setLoading(false));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, error, loading, reload: () => setTick((t) => t + 1), setData };
}
