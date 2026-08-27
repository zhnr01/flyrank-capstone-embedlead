from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    user_id: int
    tenant_id: int
