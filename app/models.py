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

    doc_id = Column(String, primary_key=True, index=True) # docID
    submit_datetime = Column(DateTime, index=True) # submitDateTime
    ordinance_code = Column(String) # ordinanceCode
    form_code = Column(String) # formCode
    doc_type_code = Column(String) # docTypeCode
    doc_description = Column(String) # docDescription
    submitter_edinet_code = Column(String, index=True) # edinetCode
    submitter_name = Column(String) # filerName
    sec_code = Column(String, index=True) # secCode (提出者の証券コード 5桁)
    jcn = Column(String) # JCN
    fund_code = Column(String) # fundCode
    issuer_edinet_code = Column(String, index=True) # issuerEdinetCode
    subject_edinet_code = Column(String, index=True) # subjectEdinetCode
    issuer_name = Column(String) # 名前解決した企業名
    withdrawal_status = Column(Integer, default=0) # withdrawalStatus
    doc_info_edit_status = Column(Integer, default=0) # docInfoEditStatus
    disclosure_status = Column(Integer, default=0) # disclosureStatus
    xbrl_flag = Column(Integer, default=0) # xbrlFlag
    pdf_flag = Column(Integer, default=0) # pdfFlag
    csv_flag = Column(Integer, default=0) # csvFlag
    legal_status = Column(Integer, default=1) # legalStatus
    processed_status = Column(Integer, default=0) # 解析ステータス (独自)

class OwnershipReport(Base):
    __tablename__ = "ownership_reports"

    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(String, ForeignKey("documents.doc_id"), unique=True)
    is_latest = Column(Integer, default=1) # 1:最新, 0:訂正等で無効
    obligation_date = Column(Date, index=True) # 報告義務発生日
    target_company_name = Column(String) # 買われた会社の名称
    holding_purpose = Column(String) # 保有目的
    holding_ratio = Column(Float) # 株券等保有割合（今回）
    prev_holding_ratio = Column(Float) # 株券等保有割合（前回）
    important_contracts = Column(String) # 担保契約等重要な契約
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class JointHolder(Base):
    __tablename__ = "joint_holders"

    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(String, ForeignKey("documents.doc_id"))
    holder_name = Column(String)
    holding_ratio = Column(Float)

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
    job_id = Column(String, nullable=True)
    message = Column(String, nullable=False)
    error_details = Column(String, nullable=True) # JSON or Stacktrace
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ImportDailyStatus(Base):
    __tablename__ = "import_daily_status"

    target_date = Column(String, primary_key=True, index=True) # 'YYYY-MM-DD'
    status = Column(String, nullable=False, default="pending") # 'pending', 'processing', 'completed', 'failed'
    total_docs_count = Column(Integer, default=0)
    target_docs_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    last_run_start_at = Column(DateTime(timezone=True))
    last_run_end_at = Column(DateTime(timezone=True))
    error_message = Column(String)
