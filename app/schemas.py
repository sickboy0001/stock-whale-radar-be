from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime

# --- User Schemas ---
class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    bio: Optional[str] = None

class User(UserBase):
    id: int
    bio: Optional[str] = None
    role_type: str
    is_admin: int
    created_at: datetime

    class Config:
        from_attributes = True

# --- Bucket Schemas ---
class BucketItemBase(BaseModel):
    stock_code: str
    order_index: int = 0

class BucketItemCreate(BucketItemBase):
    pass

class BucketItem(BucketItemBase):
    id: int
    bucket_id: int

    class Config:
        from_attributes = True

class BucketBase(BaseModel):
    name: str
    order_index: int = 0

class BucketCreate(BucketBase):
    pass

class Bucket(BucketBase):
    id: int
    user_id: int
    created_at: datetime
    items: List[BucketItem] = []

    class Config:
        from_attributes = True

# --- Auth Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# --- Sync Job Schemas ---
class SyncJobBase(BaseModel):
    job_id: str
    job_type: str
    status: str
    total_docs_found: int = 0
    target_docs_count: int = 0
    success_count: int = 0
    error_count: int = 0

class SyncJobCreate(SyncJobBase):
    pass

class SyncJob(SyncJobBase):
    started_at: datetime
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Document Task Schemas ---
class DocumentTaskBase(BaseModel):
    doc_id: str
    job_id: str
    status: str
    retry_count: int = 0
    next_retry_at: Optional[datetime] = None

class DocumentTaskCreate(DocumentTaskBase):
    pass

class DocumentTask(DocumentTaskBase):
    updated_at: datetime

    class Config:
        from_attributes = True

# --- System Event Schemas ---
class SystemEventBase(BaseModel):
    event_level: str
    event_category: str
    doc_id: Optional[str] = None
    message: str
    error_details: Optional[str] = None

class SystemEventCreate(SystemEventBase):
    pass

class SystemEvent(SystemEventBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
