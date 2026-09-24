"""Titan Text Embeddings V2 as a LangChain Embeddings, with parallel calls and token counting.

Used for both ingestion (embed_documents) and search (embed_query), so the vectors always
come from the same model and settings.
"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.config import Config
from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings

from app.config import settings

DIMENSIONS = 1024
TITAN_PRICE_PER_1K_TOKENS = 0.00002  # USD, us-east-1 on-demand


class TitanEmbeddings(Embeddings):
    def __init__(self, model_id: str, region: str, max_workers: int = 8):
        self.model_id = model_id
        self.max_workers = max_workers
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=region,
            # Adaptive retries back off automatically on ThrottlingException.
            config=Config(
                retries={"mode": "adaptive", "max_attempts": 10}, max_pool_connections=max_workers
            ),
        )
        self.tokens_used = 0
        self._lock = threading.Lock()

    def _embed(self, text: str) -> list[float]:
        body = json.dumps({"inputText": text, "dimensions": DIMENSIONS, "normalize": True})
        resp = self.client.invoke_model(modelId=self.model_id, body=body)
        data = json.loads(resp["body"].read())
        with self._lock:
            self.tokens_used += data.get("inputTextTokenCount", 0)
        return data["embedding"]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            return list(pool.map(self._embed, texts))

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    @property
    def cost_usd(self) -> float:
        return self.tokens_used / 1000 * TITAN_PRICE_PER_1K_TOKENS


def get_embeddings() -> Embeddings:
    """Real Titan in bedrock mode; deterministic fake vectors (no AWS) in fake mode."""
    if settings.llm_mode == "bedrock":
        return TitanEmbeddings(settings.embed_model_id, settings.aws_region)
    return DeterministicFakeEmbedding(size=DIMENSIONS)
