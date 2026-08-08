from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Reminder(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    title: str = Field(min_length=1, max_length=160)
    due_at: datetime
    created_at: datetime
    completed: bool = False


class ReminderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    due_at: datetime

    @field_validator("due_at")
    @classmethod
    def due_at_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("reminder due_at must include a timezone")
        return value
