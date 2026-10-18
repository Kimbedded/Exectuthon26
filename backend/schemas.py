from pydantic import BaseModel, ConfigDict, Field, model_validator


class InterpretationResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True
    )

    expression: str = Field(min_length=1, max_length=3000)
    meaning: str | None = Field(min_length=1, max_length=2000)
    translation: str | None = Field(min_length=1, max_length=3000)
    example: str | None = Field(min_length=1, max_length=2000)
    needs_clarification: bool
    clarification_question: str | None = Field(
        min_length=1, max_length=500
    )

    @model_validator(mode="after")
    def check_clarification(self):
        answers = (self.meaning, self.translation, self.example)

        if self.needs_clarification:
            if self.clarification_question is None:
                raise ValueError("A clarification question is required.")
            if any(answer is not None for answer in answers):
                raise ValueError(
                    "Answer fields must be null when clarification is needed."
                )
        else:
            if self.clarification_question is not None:
                raise ValueError(
                    "A completed answer must have a null clarification question."
                )
            if any(answer is None for answer in answers):
                raise ValueError(
                    "Meaning, translation, and example are required."
                )

        return self

class TranslationAlternative(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    context: str = Field(min_length=1)
    translation: str = Field(min_length=1)
    # Sampled from the model's own repeated choices (self-consistency), never
    # self-reported by the model; null when no probability was computed.
    probability: float | None = Field(default=None, ge=0, le=1)


class TranslationResult(BaseModel):
    """Current IDK API contract; confidence is null until calibrated."""

    model_config = ConfigDict(extra="forbid", strict=True)

    elapsed_ms: int | None = Field(ge=0)
    source_language: str = Field(min_length=2)
    target_language: str = Field(min_length=2)
    source: str = Field(min_length=1)
    translation_confidence: float | None = Field(ge=0, le=1)
    translation: str = Field(min_length=1)
    alternatives: list[TranslationAlternative] = Field(max_length=2)
class SavedTranslation(TranslationResult):
    id: int
    created_at: str


from typing import Literal
class ExtractedExpression(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal['idiom','slang','technical','word']
    text: str = Field(min_length=1)
    meaning: str = Field(min_length=1)

class EnrichedTranslationResult(TranslationResult):
    expressions: list[ExtractedExpression] = Field(max_length=4)


class ButtonAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal['translation','literal','explanation']
    text: str = Field(min_length=1)

class ButtonTranslationResult(TranslationResult):
    answers: list[ButtonAnswer] = Field(min_length=3, max_length=3)
