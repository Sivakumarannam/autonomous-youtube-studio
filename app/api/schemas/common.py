from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class SuccessResponse(BaseModel, Generic[DataT]):
    success: bool = True
    data: DataT
    message: Optional[str] = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    message: str


class PaginatedResponse(BaseModel, Generic[DataT]):
    success: bool = True
    data: list[DataT]
    total: int
    limit: int
    offset: int
    has_more: bool

    @classmethod
    def build(
        cls,
        data: list[DataT],
        total: int,
        limit: int,
        offset: int,
    ) -> "PaginatedResponse[DataT]":
        return cls(
            data=data,
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        )


class MessageResponse(BaseModel):
    success: bool = True
    message: str