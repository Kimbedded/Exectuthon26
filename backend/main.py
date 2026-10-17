from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="IDK Button")


class InterpretRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=3000)
    context: str = Field(default="", max_length=6000)
    target_language: str = Field(
        default="Spanish", min_length=2, max_length=50
    )


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