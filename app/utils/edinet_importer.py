from sqlalchemy.orm import Session
from datetime import datetime
import logging
from .. import models
from . import xbrl_parser

logger = logging.getLogger(__name__)

def import_document_to_db(db: Session, doc_id: str, xbrl_content: bytes, metadata_from_api: dict, job_id: str = None):
    """
    書類をデータベースに登録・更新（上書き）する
    """
    # 0. 先に document レコードを確保（エラー時にもステータスを更新できるようにするため）
    doc_obj = db.query(models.Document).filter(models.Document.doc_id == doc_id).first()
    if not doc_obj:
        doc_obj = models.Document(doc_id=doc_id)
        db.add(doc_obj)

    try:
        # 1. XBRL 解析
        parsed_data = xbrl_parser.parse_substantial_report(xbrl_content)
        if not parsed_data:
            logger.warning(f"Failed to parse XBRL for {doc_id}")
            doc_obj.processed_status = 9 # 解析エラー
            db.commit()
            return None

        # 2. メタデータの整理と補完
        # APIからの情報をベースに、解析結果やマスタデータで補完する
        
        # 提出者情報
        submitter_edinet_code = metadata_from_api.get("edinetCode") or parsed_data.get("submitter_edinet_code")
        submitter_name = metadata_from_api.get("filerName") or parsed_data.get("submitter_name")
        
        # 発行者（買われた会社）情報
        issuer_edinet_code = metadata_from_api.get("issuerEdinetCode")
        # issuer_edinet_code がない場合、parsed_data の issuer_sec_code から逆引きを試みる
        if not issuer_edinet_code and parsed_data.get("issuer_sec_code"):
            sec_code_4 = parsed_data.get("issuer_sec_code")[:4]
            master = db.query(models.EdinetCode).filter(models.EdinetCode.sec_code == sec_code_4).first()
            if master:
                issuer_edinet_code = master.edinet_code
        
        issuer_name = parsed_data.get("issuer_name")
        
        # マスタデータによる補完 (提出者)
        if submitter_edinet_code:
            s_master = db.query(models.EdinetCode).filter(models.EdinetCode.edinet_code == submitter_edinet_code).first()
            if s_master:
                submitter_name = submitter_name or s_master.filer_name
        
        # マスタデータによる補完 (発行者)
        if issuer_edinet_code:
            i_master = db.query(models.EdinetCode).filter(models.EdinetCode.edinet_code == issuer_edinet_code).first()
            if i_master:
                issuer_name = i_master.filer_name
        
        # ファンド情報の補完
        fund_code = metadata_from_api.get("fundCode")
        if fund_code:
            f_master = db.query(models.FundCode).filter(models.FundCode.fund_code == fund_code).first()
            if f_master:
                # ファンドの場合、発行者名としてファンド名や運用会社名を入れるケースがある
                issuer_name = issuer_name or f_master.fund_name
                if not issuer_edinet_code:
                    issuer_edinet_code = f_master.edinet_code
        
        # 3. documents テーブルへの登録 (共通メタデータ)
        # API v2 のレスポンス項目を網羅的に保存
        submit_dt_str = metadata_from_api.get("submitDateTime")
        if submit_dt_str:
            doc_obj.submit_datetime = datetime.fromisoformat(submit_dt_str.replace(" ", "T"))
        
        # 数値としての自動変換を防ぐため、明示的に str() でキャスト（特にゼロ落ち対策）
        # APIのメタデータを優先し、なければ解析結果から補完する
        doc_obj.ordinance_code = str(metadata_from_api.get("ordinanceCode") or parsed_data.get("ordinance_code") or "")
        doc_obj.form_code = str(metadata_from_api.get("formCode") or parsed_data.get("form_code") or "")
        doc_obj.doc_type_code = str(metadata_from_api.get("docTypeCode") or parsed_data.get("doc_type_code") or "")
        doc_obj.doc_description = str(metadata_from_api.get("docDescription") or parsed_data.get("doc_description") or "")
        
        # もし値が空文字列なら None にする（Nullable対応）
        if not doc_obj.ordinance_code: doc_obj.ordinance_code = None
        if not doc_obj.form_code: doc_obj.form_code = None
        if not doc_obj.doc_type_code: doc_obj.doc_type_code = None
        if not doc_obj.doc_description: doc_obj.doc_description = None

        doc_obj.submitter_edinet_code = submitter_edinet_code
        doc_obj.submitter_name = submitter_name
        doc_obj.sec_code = metadata_from_api.get("secCode") or parsed_data.get("issuer_sec_code") # どちらかあれば
        doc_obj.jcn = metadata_from_api.get("JCN") or parsed_data.get("jcn")
        doc_obj.fund_code = metadata_from_api.get("fundCode")
        doc_obj.issuer_edinet_code = issuer_edinet_code
        doc_obj.subject_edinet_code = metadata_from_api.get("subjectEdinetCode")
        doc_obj.issuer_name = issuer_name
        doc_obj.withdrawal_status = int(metadata_from_api.get("withdrawalStatus", 0))
        doc_obj.doc_info_edit_status = int(metadata_from_api.get("docInfoEditStatus", 0))
        doc_obj.disclosure_status = int(metadata_from_api.get("disclosureStatus", 0))
        doc_obj.xbrl_flag = int(metadata_from_api.get("xbrlFlag", 0))
        doc_obj.pdf_flag = int(metadata_from_api.get("pdfFlag", 0))
        doc_obj.csv_flag = int(metadata_from_api.get("csvFlag", 0))
        doc_obj.legal_status = int(metadata_from_api.get("legalStatus", 1))
        doc_obj.processed_status = 1 

        # 4. ownership_reports テーブルへの登録 (解析データ)
        report_obj = db.query(models.OwnershipReport).filter(models.OwnershipReport.doc_id == doc_id).first()
        if not report_obj:
            report_obj = models.OwnershipReport(doc_id=doc_id)
            db.add(report_obj)
        
        # 指示されたカラム名にマッピング
        report_obj.is_latest = 1 # デフォルトで最新
        
        ob_date_str = parsed_data.get("obligation_date")
        if ob_date_str:
            try:
                report_obj.obligation_date = datetime.strptime(ob_date_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        
        report_obj.target_company_name = parsed_data.get("issuer_name") # XBRLから取得した名称
        report_obj.holding_purpose = parsed_data.get("holding_purpose")
        report_obj.holding_ratio = parsed_data.get("holding_ratio")
        report_obj.prev_holding_ratio = parsed_data.get("prev_holding_ratio")
        report_obj.important_contracts = parsed_data.get("important_contracts")
        report_obj.created_at = datetime.now()

        # 5. ジョブ・タスクの管理
        if job_id:
            # 該当するタスクがあれば完了にする
            task = db.query(models.DocumentTask).filter(
                models.DocumentTask.doc_id == doc_id
            ).first()
            if task:
                task.status = 'completed'
                task.job_id = job_id
                task.updated_at = datetime.now()

        db.commit()
        db.refresh(doc_obj)
        db.refresh(report_obj)

        return {
            "document": doc_obj,
            "report": report_obj,
            "parsed": parsed_data
        }

    except Exception as e:
        db.rollback()
        logger.error(f"DB registration error for {doc_id}: {e}")
        # エラー状態を記録
        try:
            doc_obj.processed_status = 9
            # タスクがあれば失敗にする
            task = db.query(models.DocumentTask).filter(models.DocumentTask.doc_id == doc_id).first()
            if task:
                task.status = 'failed'
            db.commit()
        except:
            pass
        return None
