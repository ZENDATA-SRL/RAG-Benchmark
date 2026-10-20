import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "@/components/layout/AppLayout";
import { ChunkViewerPage } from "@/features/chunks/ChunkViewerPage";
import { ComponentsPage } from "@/features/components/ComponentsPage";
import { ConfigurationWizard } from "@/features/configurations/ConfigurationWizard";
import { ConfigurationsPage } from "@/features/configurations/ConfigurationsPage";
import { CorporaPage } from "@/features/corpora/CorporaPage";
import { CorpusDetailPage } from "@/features/corpora/CorpusDetailPage";
import { IndexesPage } from "@/features/indexes/IndexesPage";

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/corpora" replace />} />
        <Route path="/corpora" element={<CorporaPage />} />
        <Route path="/corpora/:corpusId" element={<CorpusDetailPage />} />
        <Route path="/corpora/:corpusId/documents/:documentId/chunks" element={<ChunkViewerPage />} />
        <Route path="/configurations" element={<ConfigurationsPage />} />
        <Route path="/configurations/new" element={<ConfigurationWizard />} />
        <Route path="/indexes" element={<IndexesPage />} />
        <Route path="/components" element={<ComponentsPage />} />
        <Route path="*" element={<Navigate to="/corpora" replace />} />
      </Route>
    </Routes>
  );
}
