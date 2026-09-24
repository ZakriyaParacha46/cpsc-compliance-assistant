"""Builds the real services (retriever, models, limiter) from settings.

LLM_MODE=bedrock uses Titan + Claude Haiku on Bedrock. LLM_MODE=fake uses deterministic
stand-ins so the whole app runs offline, with no AWS account.
"""

from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.config import settings
from app.limits import Limiter, PostgresStore
from app.rag import store
from app.rag.embeddings import get_embeddings
from app.rag.pipeline import Services
from app.rag.retriever import HybridRetriever, KeywordIndex


def chat_models() -> tuple[BaseChatModel, BaseChatModel]:
    """(classifier, answer) models."""
    if settings.llm_mode == "bedrock":
        from langchain_aws import ChatBedrockConverse

        common = {"model": settings.answer_model_id, "region_name": settings.aws_region}
        classifier = ChatBedrockConverse(**common, temperature=0, max_tokens=3)
        answer = ChatBedrockConverse(**common, temperature=0, max_tokens=settings.max_output_tokens)
        return classifier, answer
    return (
        FakeListChatModel(responses=["IN"]),
        FakeListChatModel(
            responses=["Fake mode answer, built from the first retrieved source only [1]."]
        ),
    )


def build_services() -> Services:
    store.ensure_app_schema()
    retriever = HybridRetriever(
        vector_store=store.vector_store(get_embeddings()),
        keyword_index=KeywordIndex(store.all_chunks()),
        k=settings.max_chunks,
        max_guidance=settings.max_guidance,
        max_guidance_per_page=settings.max_guidance_per_page,
    )
    classifier, answer = chat_models()
    return Services(
        retriever=retriever,
        classifier_llm=classifier,
        answer_llm=answer,
        limiter=Limiter(PostgresStore(settings.database_url)),
        log_query=store.insert_query_log,
    )
