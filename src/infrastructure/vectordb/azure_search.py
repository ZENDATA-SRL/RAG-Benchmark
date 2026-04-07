import os

from azure.search.documents import SearchClient
from dotenv import load_dotenv

load_dotenv()


def get_azure_search_client() -> SearchClient:
    endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
    key = os.getenv("AZURE_SEARCH_KEY")
    index_name = os.getenv("AZURE_SEARCH_INDEX_NAME")
    if not endpoint or not key or not index_name:
        raise ValueError(
            "AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_KEY, and AZURE_SEARCH_INDEX_NAME must be set"
        )
    return SearchClient(endpoint, key, index_name)
