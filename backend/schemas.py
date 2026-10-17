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