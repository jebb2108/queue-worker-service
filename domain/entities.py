from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    user_id: int
    language: str
    fluency: int