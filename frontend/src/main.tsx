import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import Workspace from "./components/Workspace";
import { HelixLoader } from "./components/ui";
import { AnalysisProvider } from "./lib/analysis";
import { ThemeProvider } from "./lib/theme";
import Landing from "./pages/Landing";
import "./index.css";

// Each research module is its own chunk (lazy loading).
const CommandCenter = lazy(() => import("./pages/workspace/CommandCenter"));
const VariantExplorer = lazy(() => import("./pages/workspace/VariantExplorer"));
const PathogenicityLab = lazy(() => import("./pages/workspace/PathogenicityLab"));
const PopulationObservatory = lazy(() => import("./pages/workspace/PopulationObservatory"));
const ConstraintObservatory = lazy(() => import("./pages/workspace/ConstraintObservatory"));
const AnomalyEngine = lazy(() => import("./pages/workspace/AnomalyEngine"));
const StatisticsStudio = lazy(() => import("./pages/workspace/StatisticsStudio"));
const SyntheticLab = lazy(() => import("./pages/workspace/SyntheticLab"));
const Reports = lazy(() => import("./pages/workspace/Reports"));
const HistoryPage = lazy(() => import("./pages/workspace/History"));

const S = ({ children }: { children: React.ReactNode }) => (
  <Suspense fallback={<div className="py-20"><HelixLoader label="Loading module" /></div>}>{children}</Suspense>
);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider>
      <AnalysisProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/workspace" element={<Workspace />}>
              <Route index element={<S><CommandCenter /></S>} />
              <Route path="variants" element={<S><VariantExplorer /></S>} />
              <Route path="pathogenicity" element={<S><PathogenicityLab /></S>} />
              <Route path="populations" element={<S><PopulationObservatory /></S>} />
              <Route path="constraint" element={<S><ConstraintObservatory /></S>} />
              <Route path="anomalies" element={<S><AnomalyEngine /></S>} />
              <Route path="statistics" element={<S><StatisticsStudio /></S>} />
              <Route path="synthetic" element={<S><SyntheticLab /></S>} />
              <Route path="reports" element={<S><Reports /></S>} />
              <Route path="history" element={<S><HistoryPage /></S>} />
            </Route>
            <Route path="*" element={<Landing />} />
          </Routes>
        </BrowserRouter>
      </AnalysisProvider>
    </ThemeProvider>
  </React.StrictMode>,
);
