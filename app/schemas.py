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
