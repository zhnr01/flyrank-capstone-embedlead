from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SubmissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    message: str | None = Field(default=None, max_length=2_000)


class SubmissionAccepted(BaseModel):
    status: str = "accepted"
