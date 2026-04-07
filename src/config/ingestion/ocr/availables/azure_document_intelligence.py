import os

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential

from config.ingestion.ocr.base import BaseOCR


class AzureDocumentIntelligenceOCR(BaseOCR):
    def __init__(self) -> None:
        self._client = DocumentIntelligenceClient(
            endpoint=os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"),
            credential=AzureKeyCredential(
                os.getenv("AZURE_DOCUMENT_INTELLIGENCE_API_KEY")
            ),
        )

    def extract_text(self, file_path: str) -> str:
        with open(file_path, "rb") as f:
            document_bytes = f.read()
        poller = self._client.begin_analyze_document(
            "prebuilt-document", body=AnalyzeDocumentRequest(document_bytes)
        )
        result = poller.result()
        return result.content
