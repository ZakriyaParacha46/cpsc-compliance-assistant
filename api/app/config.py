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

    # Usage limits (PRD: Usage limits per user)
    limit_per_visitor_day: int = 20
    limit_per_ip_day: int = 40
    limit_burst_per_minute: int = 5
    limit_global_day: int = 500
    max_question_chars: int = 500
    max_output_tokens: int = 800
    max_chunks: int = 6


settings = Settings()
