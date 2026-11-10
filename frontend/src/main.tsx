import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Workspace from "./components/Workspace";
import { HelixLoader } from "./components/ui";
import { AnalysisProvider } from "./lib/analysis";
import { ProvenanceProvider } from "./lib/provenance";
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
const GeneComparisonLab = lazy(() => import("./pages/workspace/GeneComparisonLab"));
const SourceManager = lazy(() => import("./pages/workspace/SourceManager"));
const CustomDatasetLab = lazy(() => import("./pages/workspace/CustomDatasetLab"));

const S = ({ children }: { children: React.ReactNode }) => (
  <Suspense fallback={<div className="py-20"><HelixLoader label="Loading module" /></div>}>{children}</Suspense>
);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider>
      <AnalysisProvider>
       <ProvenanceProvider>
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
              <Route path="compare" element={<S><GeneComparisonLab /></S>} />
              <Route path="sources" element={<S><SourceManager /></S>} />
              <Route path="custom" element={<S><CustomDatasetLab /></S>} />
              {/* History & Provenance now lives inside the Report Generator */}
              <Route path="history" element={<Navigate to="/workspace/reports" replace />} />
            </Route>
            <Route path="*" element={<Landing />} />
          </Routes>
        </BrowserRouter>
       </ProvenanceProvider>
      </AnalysisProvider>
    </ThemeProvider>
  </React.StrictMode>,
);
