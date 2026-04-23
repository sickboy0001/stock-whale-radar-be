from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Date, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    bio = Column(String)
    role_type = Column(String, default="free")
    is_admin = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    buckets = relationship("Bucket", back_populates="owner")

class Bucket(Base):
    __tablename__ = "buckets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    order_index = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="buckets")
    items = relationship("BucketItem", back_populates="bucket")

class BucketItem(Base):
    __tablename__ = "bucket_items"

    id = Column(Integer, primary_key=True, index=True)
    bucket_id = Column(Integer, ForeignKey("buckets.id"))
    stock_code = Column(String, nullable=False)
    order_index = Column(Integer, default=0)

    bucket = relationship("Bucket", back_populates="items")

class EdinetCode(Base):
    __tablename__ = "edinet_codes"

    edinet_code = Column(String, primary_key=True, index=True)
    submitter_type = Column(String)
    listing_status = Column(String)
    consolidated = Column(String)
    capital = Column(Integer)
    settlement_date = Column(String)
    filer_name = Column(String, nullable=False)
    filer_name_en = Column(String)
    filer_name_kana = Column(String)
    address = Column(String)
    industry = Column(String)
    sec_code = Column(String, index=True)
    jcn = Column(String)

class FundCode(Base):
    __tablename__ = "fund_codes"

    fund_code = Column(String, primary_key=True, index=True)
    sec_code = Column(String, index=True)
    fund_name = Column(String, nullable=False)
    fund_name_kana = Column(String)
    security_type = Column(String)
    period_1 = Column(String)
    period_2 = Column(String)
    edinet_code = Column(String, ForeignKey("edinet_codes.edinet_code"))
    issuer_name = Column(String)

class Document(Base):
    __tablename__ = "documents"

    doc_id = Column(String, primary_key=True, index=True)
    seq_number = Column(Integer)
    submit_date_time = Column(DateTime, index=True)
    edinet_code = Column(String, ForeignKey("edinet_codes.edinet_code"))
    doc_description = Column(String)
    doc_type_code = Column(String)
    parent_doc_id = Column(String)
    withdrawal_status = Column(Integer, default=0)
    legal_status = Column(Integer)

class SubstantialReport(Base):
    __tablename__ = "substantial_reports"

    doc_id = Column(String, ForeignKey("documents.doc_id"), primary_key=True)
    obligation_date = Column(Date, index=True)
    issuer_edinet_code = Column(String, index=True)
    issuer_name = Column(String)
    holding_ratio = Column(Float)
    prev_holding_ratio = Column(Float)
    holding_purpose = Column(String)
    total_number_of_shares = Column(Integer)

class JointHolder(Base):
    __tablename__ = "joint_holders"

    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(String, ForeignKey("documents.doc_id"))
    filer_edinet_code = Column(String)
    individual_holding_ratio = Column(Float)
    context_ref = Column(String)

class SyncJob(Base):
    __tablename__ = "sync_jobs"

    job_id = Column(String, primary_key=True, index=True)
    job_type = Column(String, nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True))
    status = Column(String, nullable=False) # 'running', 'success', 'failed'
    total_docs_found = Column(Integer, default=0)
    target_docs_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)

class DocumentTask(Base):
    __tablename__ = "document_tasks"

    doc_id = Column(String, primary_key=True, index=True)
    job_id = Column(String, ForeignKey("sync_jobs.job_id"), nullable=False)
    status = Column(String, nullable=False) # 'pending', 'processing', 'completed', 'failed'
    retry_count = Column(Integer, default=0)
    next_retry_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

class SystemEvent(Base):
    __tablename__ = "system_events"

    id = Column(Integer, primary_key=True, index=True)
    event_level = Column(String, nullable=False) # 'INFO', 'WARN', 'ERROR', 'FATAL'
    event_category = Column(String, nullable=False) # 'batch_sync', 'xbrl_parse', 'api_fetch', 'system'
    doc_id = Column(String, nullable=True)
    message = Column(String, nullable=False)
    error_details = Column(String, nullable=True) # JSON or Stacktrace
    created_at = Column(DateTime(timezone=True), server_default=func.now())
