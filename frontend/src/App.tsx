import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "@/components/layout/AppLayout";
import { ChunkViewerPage } from "@/features/chunks/ChunkViewerPage";
import { ComponentsPage } from "@/features/components/ComponentsPage";
import { ConfigurationWizard } from "@/features/configurations/ConfigurationWizard";
import { ConfigurationsPage } from "@/features/configurations/ConfigurationsPage";
import { CorporaPage } from "@/features/corpora/CorporaPage";
import { CorpusDetailPage } from "@/features/corpora/CorpusDetailPage";
import { ExperimentDetailPage } from "@/features/experiments/ExperimentDetailPage";
import { ExperimentsPage } from "@/features/experiments/ExperimentsPage";
import { RunPage } from "@/features/experiments/RunPage";
import { IndexesPage } from "@/features/indexes/IndexesPage";

import { AnnotationPage } from "@/features/qa-sets/AnnotationPage";
import { QaSetDetailPage } from "@/features/qa-sets/QaSetDetailPage";
import { QaSetsPage } from "@/features/qa-sets/QaSetsPage";

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/corpora" replace />} />
        <Route path="/corpora" element={<CorporaPage />} />
        <Route path="/corpora/:corpusId" element={<CorpusDetailPage />} />
        <Route
          path="/corpora/:corpusId/documents/:documentId/chunks"
          element={<ChunkViewerPage />}
        />
        <Route path="/configurations" element={<ConfigurationsPage />} />
        <Route path="/configurations/new" element={<ConfigurationWizard />} />
        <Route path="/indexes" element={<IndexesPage />} />
        <Route path="/qa-sets" element={<QaSetsPage />} />
        <Route path="/qa-sets/:qaSetId" element={<QaSetDetailPage />} />
        <Route
          path="/qa-sets/:qaSetId/questions/:questionId/annotate"
          element={<AnnotationPage />}
        />
        <Route path="/experiments" element={<ExperimentsPage />} />
        <Route path="/experiments/:experimentId" element={<ExperimentDetailPage />} />
        <Route path="/experiments/:experimentId/runs/:runId" element={<RunPage />} />
        <Route path="/components" element={<ComponentsPage />} />
        <Route path="*" element={<Navigate to="/corpora" replace />} />
      </Route>
    </Routes>
  );
}
