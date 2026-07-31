import enum

from sqlalchemy import Enum as SAEnum


class StrEnum(str, enum.Enum):
    pass


def SqlEnum(enum_cls):
    return SAEnum(
        enum_cls,
        values_callable=lambda cls: [e.value for e in cls],
        native_enum=True,
    )