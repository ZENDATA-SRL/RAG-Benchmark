import os
from uuid import UUID

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import AzureChatOpenAI

from src.config.llms.repository import get_llm_repository
from src.config.llms.schemas import LLMConfig, LLMConfigSchema


def build_llm(llm_config: LLMConfigSchema) -> BaseChatModel:
    if llm_config.provider == "openai":
        # Treat "openai" as Azure OpenAI for this project.
        load_dotenv(override=True)
        api_version = os.getenv("AZURE_OPENAI_API_VERSION")
        azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        if not api_version:
            raise RuntimeError("OPENAI_API_VERSION is not set for Azure OpenAI.")
        if not azure_deployment:
            raise RuntimeError("AZURE_OPENAI_DEPLOYMENT is not set for Azure OpenAI.")

        # Keep the selected model name for tracing/token counting,
        # while using Azure deployment for routing.
        return AzureChatOpenAI(
            azure_deployment=azure_deployment,
            api_version=api_version,
            model=llm_config.model,
        )

    return init_chat_model(model=llm_config.model, model_provider=llm_config.provider)


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
