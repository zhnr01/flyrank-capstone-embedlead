from typing import Literal

from pydantic import BaseModel

SubmissionStatus = Literal["accepted"]
ACCEPTED_STATUS: SubmissionStatus = "accepted"


class SubmissionAccepted(BaseModel):
    status: SubmissionStatus = ACCEPTED_STATUS
