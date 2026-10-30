from dataclasses import dataclass
from enum import IntEnum


class ClassificationLabel(IntEnum):
    LEFT = 0
    RIGHT = 1


@dataclass(frozen=True)
class ReviewDocument:
    id: str
    filename: str
    display_name: str
    media_type: str = "application/pdf"
