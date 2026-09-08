from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    name: str
    target_platform: Literal["d365", "salesforce"]


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    target_platform: str
    status: str
    has_draft: bool = False
    created_at: datetime
    updated_at: datetime


class UploadedFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    type: str
    filename: str
    uploaded_at: datetime
    processed_at: Optional[datetime] = None


class ProjectDetailOut(ProjectOut):
    uploaded_files: list[UploadedFileOut] = []
