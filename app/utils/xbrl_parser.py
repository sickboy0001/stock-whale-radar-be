from lxml import etree
import io

def parse_substantial_report(xbrl_content: bytes):
    """
    大量保有報告書の XBRL を解析する (jplvh_cor, jpdei_cor 等に対応)
    """
    try:
        tree = etree.parse(io.BytesIO(xbrl_content))
        root = tree.getroot()
        
        # プレフィックスに依存しないローカル名での検索関数
        def get_value(local_name):
            elements = root.xpath(f"//*[local-name()='{local_name}']")
            return elements[0].text if elements else None

        # 1. 提出者情報
        submitter_name = get_value('FilerNameInJapaneseDEI') or get_value('FilerNameOwnershipReport')
        submitter_edinet_code = get_value('EDINETCodeDEI')
        jcn = get_value('CorporationNumberDEI')

        # 2. 書類メタデータ (DEI)
        ordinance_code = get_value('OrdinanceCodeDEI')
        form_code = get_value('FormCodeDEI')
        doc_type_code = get_value('DocumentTypeCodeDEI')
        doc_description = get_value('DocumentTitleDEI') or get_value('DocumentDescriptionDEI')

        # 3. 発行者情報
        issuer_name = get_value('NameOfIssuer')
        issuer_sec_code = get_value('SecurityCodeOfIssuer')

        # 3. 保有状況 (指示されたタグ名を優先)
        # 報告義務発生日: DateOnWhichDutyToReportArose
        obligation_date = get_value('DateOnWhichDutyToReportArose') or get_value('DateWhenFilingRequirementAroseCoverPage')
        
        # 保有目的: PurposeOfHolding
        holding_purpose = get_value('PurposeOfHolding') or get_value('PurposeOfHoldingOwnershipReport')

        # 株券等保有割合（今回）: ProportionOfSharesHeld
        holding_ratio_raw = get_value('ProportionOfSharesHeld') or get_value('HoldingRatioOfShareCertificatesEtc')
        holding_ratio = float(holding_ratio_raw) * 100 if holding_ratio_raw else 0.0
        
        # 株券等保有割合（前回）: ProportionOfSharesHeldInPreviousReport
        prev_ratio_raw = get_value('ProportionOfSharesHeldInPreviousReport') or get_value('HoldingRatioOfShareCertificatesEtcPerLastReport')
        prev_holding_ratio = float(prev_ratio_raw) * 100 if prev_ratio_raw else 0.0

        # 担保契約等重要な契約: ImportantContractsRegardingSaidShareCertificatesEtc
        important_contracts = get_value('ImportantContractsRegardingSaidShareCertificatesEtc')

        # 共同保有者の有無
        total_holders = get_value('TotalNumberOfFilersAndJointHoldersCoverPage')
        is_joint_holding = 1 if (total_holders and int(total_holders) > 1) else 0

        return {
            "submitter_name": submitter_name,
            "submitter_edinet_code": submitter_edinet_code,
            "jcn": jcn,
            "ordinance_code": ordinance_code,
            "form_code": form_code,
            "doc_type_code": doc_type_code,
            "doc_description": doc_description,
            "issuer_name": issuer_name,
            "issuer_sec_code": issuer_sec_code,
            "obligation_date": obligation_date,
            "holding_ratio": round(holding_ratio, 2),
            "prev_holding_ratio": round(prev_holding_ratio, 2),
            "holding_purpose": holding_purpose,
            "important_contracts": important_contracts,
            "is_joint_holding": is_joint_holding
        }
    except Exception as e:
        print(f"XBRL Parse Error: {e}")
        return None
