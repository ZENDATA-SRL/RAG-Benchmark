from uuid import UUID
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from config.llms.models import LLMConfigORM
from config.llms.repository import get_llm_repository
from config.llms.schemas import LLMConfig, LLMConfigSchema


def build_llm(provider: str, model: str) -> BaseChatModel:
    return init_chat_model(model=model, model_provider=provider)


async def resolve_llm(llm: LLMConfigSchema) -> LLMConfig:
    repository = get_llm_repository()
    llm_object = await repository.get_llm_by_config(llm)
    if llm_object:
        return LLMConfig.model_validate(llm_object)
    created = await repository.insert_llm_config(llm)
    return LLMConfig.model_validate(created)


async def get_llm_by_id(llm_id: UUID) -> LLMConfig:
    repository = get_llm_repository()
    obj = await repository.get_llm_by_id(llm_id)
    if obj is None:
        raise ValueError(f"LLM config {llm_id} not found")
    return LLMConfig.model_validate(obj)
