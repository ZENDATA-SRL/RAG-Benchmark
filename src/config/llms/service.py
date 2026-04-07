from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from config.llms.models import LLMConfig
from config.llms.repository import get_llm_repository
from config.llms.schemas import LLMConfigSchema


def build_llm(provider: str, model: str) -> BaseChatModel:
    return init_chat_model(model=model, model_provider=provider)


async def resolve_llm(llm: LLMConfigSchema) -> LLMConfig:
    repository = get_llm_repository()
    llm_object = await repository.get_llm_by_config(llm)
    if llm_object:
        return llm_object
    llm_config = LLMConfigSchema(
        provider=llm.provider,
        model=llm.model,
    )
    return await repository.insert_llm_config(llm_config)
