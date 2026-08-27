from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SubmissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    message: str | None = Field(default=None, max_length=2_000)
    website: str | None = Field(default=None, max_length=200)

    @property
    def looks_automated(self) -> bool:
        return bool(self.website and self.website.strip())


class SubmissionAccepted(BaseModel):
    status: str = "accepted"
