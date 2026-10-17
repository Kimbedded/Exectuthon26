from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from pydantic import BaseModel, ConfigDict, Field

from database import init_db, list_expressions, save_expression


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="IDK Button", lifespan=lifespan)


class InterpretRequest(BaseModel):
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


@app.post("/interpret")
def interpret(request: InterpretRequest):
    return {
        "status": "received",
        "transcript": request.transcript,
        "context": request.context,
        "target_language": request.target_language
    }


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