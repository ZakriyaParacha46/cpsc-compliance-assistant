from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime config comes from environment variables (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "local"  # local | ci | prod
    database_url: str = "postgresql://cpsc:cpsc@localhost:5432/cpsc"
    aws_region: str = "us-east-1"

    # "fake" returns canned Bedrock responses so the app runs offline and in CI.
    llm_mode: str = "fake"  # fake | bedrock
    answer_model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    embed_model_id: str = "amazon.titan-embed-text-v2:0"

    # Data and storage
    data_dir: str = "data"  # raw downloads live under data/raw/
    data_bucket: str = ""  # S3 bucket for raw copies and backups; empty = local only
    collection_name: str = "cpsc"  # pgvector collection
    govinfo_api_key: str = "DEMO_KEY"  # api.data.gov key; DEMO_KEY is enough for a few calls

    # Usage limits (PRD: Usage limits per user)
    limit_per_visitor_day: int = 20
    limit_per_ip_day: int = 40
    limit_burst_per_minute: int = 5
    limit_global_day: int = 500
    max_question_chars: int = 500
    max_output_tokens: int = 800
    max_chunks: int = 6
    # "Not covered" without calling the model when even the closest chunk is further than
    # this (cosine distance, 0 = identical). Tuned with `python -m eval.retrieval`.
    relevance_max_distance: float = 0.61

    # Retrieval balance (see eval results): guidance can't crowd out rules and laws.
    max_guidance: int = 3
    max_guidance_per_page: int = 2

    # Visitors (no login): random id in an HTTP-only cookie, backed by the client IP.
    visitor_cookie: str = "cpsc_vid"
    # Proxies in front of the API that append to X-Forwarded-For. 0 = none (dev / tunnel).
    # Prod: 2 (CloudFront, then Caddy), so the real client is the 2nd entry from the end.
    trusted_proxy_hops: int = 0


settings = Settings()
