from config.llms.models import LLMConfig
from config.llms.schemas import LLMConfigSchema


class LLMRepository:
    async def get_llm_by_config(self, llm: LLMConfigSchema) -> LLMConfig | None:
        pass

    async def insert_llm_config(self, llm: LLMConfigSchema) -> LLMConfig:
        pass


def get_llm_repository() -> LLMRepository:
    return LLMRepository()
