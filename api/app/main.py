import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import settings

app = FastAPI(
    title="CPSC Compliance Assistant", docs_url="/api/docs", openapi_url="/api/openapi.json"
)


def _db_ok() -> bool:
    try:
        with psycopg.connect(settings.database_url, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        return True
    except psycopg.Error:
        return False


@app.get("/api/health")
def health() -> JSONResponse:
    checks = {"db": _db_ok(), "llm_mode": settings.llm_mode}
    status = 200 if checks["db"] else 503
    return JSONResponse(
        {"status": "ok" if status == 200 else "degraded", "env": settings.env, **checks},
        status_code=status,
    )
