/**
 * Theme-aware Plotly wrapper. Plotly is code-split (large bundle) and loaded
 * on first use; a skeleton shows while it loads. Layout defaults follow the
 * GeneLens tokens: recessive grid, muted axis text, transparent surfaces.
 */
import { lazy, Suspense, useMemo } from "react";
import type { Config, Data, Layout } from "plotly.js";
import { useTheme } from "../lib/theme";
import { token } from "../lib/format";

const LazyPlot = lazy(async () => {
  const [{ default: Plotly }, { default: factory }] = await Promise.all([
    import("plotly.js-cartesian-dist-min"),
    import("react-plotly.js/factory"),
  ]);
  return { default: factory(Plotly) };
});

export function ChartSkeleton({ height = 320 }: { height?: number }) {
  return (
    <div className="relative overflow-hidden rounded-xl bg-raised/60" style={{ height }} aria-busy="true" aria-label="Loading chart">
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_1.6s_infinite] bg-gradient-to-r from-transparent via-accent/10 to-transparent" />
      <style>{`@keyframes shimmer { 100% { transform: translateX(100%); } }`}</style>
    </div>
  );
}

export default function Plot({ data, layout, height = 320, config }: {
  data: Data[]; layout?: Partial<Layout>; height?: number; config?: Partial<Config>;
}) {
  const { theme } = useTheme();
  const merged = useMemo<Partial<Layout>>(() => {
    const ink = token("muted"); const grid = token("line", 0.7);
    const axis = { gridcolor: grid, zerolinecolor: grid, linecolor: grid, tickfont: { color: ink, size: 11 }, title: { font: { color: ink, size: 12 } }, automargin: true };
    return {
      height, autosize: true, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: "Inter, system-ui, sans-serif", color: token("ink"), size: 12 },
      margin: { l: 56, r: 16, t: 36, b: 48 },
      hoverlabel: { bgcolor: token("raised"), bordercolor: token("line"), font: { color: token("ink"), family: "JetBrains Mono, monospace", size: 11 } },
      // Legends sit above the plot so they never collide with x-axis titles.
      legend: { orientation: "h", x: 0, xanchor: "left", y: 1.02, yanchor: "bottom", font: { color: ink, size: 11 } },
      transition: { duration: 500, easing: "cubic-in-out" },
      ...layout,
      xaxis: { ...axis, ...(layout?.xaxis ?? {}) },
      yaxis: { ...axis, ...(layout?.yaxis ?? {}) },
    };
    // theme in deps: tokens change when the theme flips
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, height, theme]);
  return (
    <Suspense fallback={<ChartSkeleton height={height} />}>
      <LazyPlot data={data} layout={merged} useResizeHandler style={{ width: "100%", height }}
        config={{ displaylogo: false, responsive: true, modeBarButtonsToRemove: ["lasso2d", "select2d"], ...config }} />
    </Suspense>
  );
}
