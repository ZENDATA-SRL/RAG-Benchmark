from azure.cosmos import CosmosClient


def get_cosmos_client(url: str, key: str) -> CosmosClient:
    return CosmosClient(url, key)
