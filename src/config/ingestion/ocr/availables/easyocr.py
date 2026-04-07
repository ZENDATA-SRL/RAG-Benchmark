import base64
from io import BytesIO
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pdf2image import convert_from_path
from PIL import Image

from config.ingestion.ocr.base import BaseOCR
from config.llms.service import build_llm

_TEXT_EXTRACTION_PROMPT = (
    "Extract all visible text from this image. Preserve reading order and line breaks "
    "where it aids readability. Output only the extracted text, with no preamble or commentary."
)


class GeminiOCR(BaseOCR):
    """Document OCR via Gemini vision using `build_llm` (LangChain)."""

    def __init__(
        self,
        provider: str = "google_genai",
        model: str = "gemini-2.5-flash",
    ) -> None:
        self._provider = provider
        self._model = model
        self._llm: BaseChatModel | None = None

    def _get_llm(self) -> BaseChatModel:
        if self._llm is None:
            self._llm = build_llm(provider=self._provider, model=self._model)
        return self._llm

    def extract_text(self, file_path: str) -> str:
        path = Path(file_path)
        if path.suffix.lower() != ".pdf":
            with Image.open(path) as im:
                return self._ocr(im)
        parts: list[str] = []
        for im in convert_from_path(path):
            parts.append(self._ocr(im))
        return "\n\n".join(p for p in parts if p)

    def _ocr(self, image: Image.Image) -> str:
        buffer = BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        b64 = base64.standard_b64encode(buffer.getvalue()).decode("ascii")
        data_url = f"data:image/png;base64,{b64}"

        messages = [
            SystemMessage(content=_TEXT_EXTRACTION_PROMPT),
            HumanMessage(
                content={
                    "type": "image_url",
                    "image_url": {"url": data_url},
                },
            ),
        ]
        response = self._get_llm().invoke(messages)
        text = response.content
        if isinstance(text, list):
            text = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in text
            )
        return str(text).strip()
