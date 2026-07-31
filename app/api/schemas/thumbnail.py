from uuid import UUID

from pydantic import BaseModel

from app.database.models.thumbnail import ThumbnailStatus


class ThumbnailGenerateRequest(BaseModel):
    script_id: UUID


class ThumbnailUpdateRequest(BaseModel):
    concept: str | None = None
    file_path: str | None = None
    status: ThumbnailStatus | None = None


class ThumbnailResponse(BaseModel):
    id: UUID
    script_id: UUID
    concept: str | None
    file_path: str | None
    status: ThumbnailStatus

    model_config = {
        "from_attributes": True,
    }


class ThumbnailGenerateResponse(BaseModel):
    id: UUID
    script_id: UUID
    concept: str | None
    file_path: str | None
    status: ThumbnailStatus

    model_config = {
        "from_attributes": True,
    }


class DeleteResponse(BaseModel):
    message: str