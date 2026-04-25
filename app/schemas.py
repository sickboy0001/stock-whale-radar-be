from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime, date

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

# --- Import Daily Status Schemas ---
class ImportDailyStatusBase(BaseModel):
    target_date: str
    status: str
    total_docs_count: int = 0
    target_docs_count: int = 0
    success_count: int = 0
    error_message: Optional[str] = None

class ImportDailyStatusCreate(ImportDailyStatusBase):
    pass

class ImportDailyStatus(ImportDailyStatusBase):
    last_run_start_at: Optional[datetime] = None
    last_run_end_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Document Schemas ---
class DocumentBase(BaseModel):
    doc_id: str
    submit_datetime: Optional[datetime] = None
    ordinance_code: Optional[str] = None
    form_code: Optional[str] = None
    doc_type_code: Optional[str] = None
    doc_description: Optional[str] = None
    submitter_edinet_code: Optional[str] = None
    submitter_name: Optional[str] = None
    sec_code: Optional[str] = None
    jcn: Optional[str] = None
    fund_code: Optional[str] = None
    issuer_edinet_code: Optional[str] = None
    subject_edinet_code: Optional[str] = None
    issuer_name: Optional[str] = None
    withdrawal_status: int = 0
    doc_info_edit_status: int = 0
    disclosure_status: int = 0
    xbrl_flag: int = 0
    pdf_flag: int = 0
    csv_flag: int = 0
    legal_status: int = 1
    processed_status: int = 0

class DocumentCreate(DocumentBase):
    pass

class Document(DocumentBase):
    class Config:
        from_attributes = True

# --- Ownership Report Schemas ---
class OwnershipReportBase(BaseModel):
    doc_id: str
    is_latest: int = 1
    obligation_date: Optional[date] = None
    target_company_name: Optional[str] = None
    holding_purpose: Optional[str] = None
    holding_ratio: Optional[float] = None
    prev_holding_ratio: Optional[float] = None
    important_contracts: Optional[str] = None

class OwnershipReportCreate(OwnershipReportBase):
    pass

class OwnershipReport(OwnershipReportBase):
    id: int
    created_at: datetime
    class Config:
        from_attributes = True
