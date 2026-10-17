from contextlib import asynccontextmanager
import json
from urllib.error import URLError

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from database import init_db, list_expressions, save_expression
from idk_client import interpret as interpret_ai
from schemas import TranslationResult


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="IDK Button", lifespan=lifespan)


class InterpretRequest(BaseModel):
    source_language: str = Field(default="en", min_length=2, max_length=50)
    elapsed_ms: int | None = Field(default=None, ge=0, strict=True)
    transcript: str = Field(min_length=1, max_length=3000)
    context: str = Field(default="", max_length=6000)
    target_language: str = Field(
        default="Spanish", min_length=2, max_length=50
    )


class SaveExpressionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True
    )

    expression: str = Field(min_length=1, max_length=3000)
    meaning: str = Field(min_length=1, max_length=2000)
    translation: str = Field(min_length=1, max_length=3000)
    example: str = Field(min_length=1, max_length=2000)
    target_language: str = Field(min_length=2, max_length=50)


class SavedExpression(SaveExpressionRequest):
    id: int
    created_at: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/interpret", response_model=TranslationResult)
def interpret(request: InterpretRequest):
    try:
        return interpret_ai(
            transcript=request.transcript,
            context=request.context,
            target_language=request.target_language,
            source_language=request.source_language,
            elapsed_ms=request.elapsed_ms,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="AI request timed out") from exc
    except (json.JSONDecodeError, RuntimeError, URLError) as exc:
        raise HTTPException(status_code=502, detail="AI request failed") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/expressions",
    response_model=SavedExpression,
    status_code=201
)
def create_expression(request: SaveExpressionRequest):
    return save_expression(**request.model_dump())


@app.get("/expressions", response_model=list[SavedExpression])
def get_expressions(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0)
):
    return list_expressions(limit=limit, offset=offset)