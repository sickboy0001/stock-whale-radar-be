
## 概要

Githubactionで定期的に、CloudRunをAPIキックして、
EdiNetのEdiCode,Fundcodeを入手する仕組みを想定しています。

GithubActionからCloudRunのAPIキックの動きは実装済みなので、
それを変える形を想定しています。


### 📥 EDINET公式 マスタデータ・ダウンロードURL

#### 🏢 EDINETコードリスト（企業等のリスト）
*   **日本語リスト（ZIP形式）**
    `https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Edinetcode.zip`

#### 💰 ファンドコードリスト（投資信託等のリスト）
*   **日本語リスト（ZIP形式）**
    `https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Fundcode.zip`

---

### 💡 ダウンロード＆パース実装時の超重要ポイント（罠）

このCSVファイルをPythonでパースしてTursoに落とし込む際、**3つの特殊な仕様（罠）**があります。事前に把握しておかないとエラーになります。

#### 1. 1行目と2行目は「データではない」
EDINETからダウンロードしたZIP内のCSVを開くと、以下のような構成になっています。
*   **1行目**: `ダウンロード実行日,2026年04月21日現在,件数,11238件` （メタデータ）
*   **2行目**: `ＥＤＩＮＥＴコード,提出者種別,上場区分,...` （ヘッダー行）
*   **3行目以降**: 実際のデータ

そのため、Python（Pandas等）で読み込む際は、**必ず1行目をスキップ（`skiprows=1`）し、2行目をヘッダーとして扱う**必要があります。

#### 2. 文字コードは「Shift-JIS (cp932)」
日本の官公庁のCSVデータのお約束として、文字コードは `UTF-8` ではなく `Shift-JIS`（Pythonでは `cp932` を指定するのが最も安全）です。

#### 3. 「ファンドコード」は別のCSVに分かれている
以前のご質問の中で「EDINETコードのCSVの中からファンドを抽出する」という案がありましたが、仕様書にある通り、**ファンド（投資信託）のリストは `Fundcode.zip` として完全に別のファイル**で提供されています。
そのため、バッチ処理では `Edinetcode.zip` と `Fundcode.zip` の**両方のURLにリクエストを送って、別々のテーブルにUPSERTする**必要があります。

---

### 🛠️ 修正版：FastAPI側の実装ロジック案

上記の罠をクリアし、GitHub Actionsからキックされる想定の安全な実装コード案です。
（※Pandasはメモリを食うため、Python標準の `csv` と `io.TextIOWrapper` を使うとCloud Runに優しく、メモリを数MBしか消費しません）

```python
import httpx
import zipfile
import io
import csv
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
# ... (既存の認証やDB設定をインポート) ...

router = APIRouter(prefix="/admin/master_sync", tags=["master_sync"])

EDINET_CODE_URL = "https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Edinetcode.zip"
FUND_CODE_URL = "https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Fundcode.zip"

async def download_and_parse_csv(url: str):
    """URLからZIPをDLし、中のCSVをパースして辞書のリストを返す"""
    async with httpx.AsyncClient() as client:
        # EDINETのサーバーは少し遅いことがあるのでtimeoutは長めに
        response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60.0)
        response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        # ZIP内の最初のファイル(CSV)を開く
        csv_filename = z.namelist()[0]
        with z.open(csv_filename) as f:
            # Shift-JIS(cp932)でデコード
            text_stream = io.TextIOWrapper(f, encoding='cp932')
            
            # 1行目（ダウンロード実行日...）をスキップ
            next(text_stream)
            
            # 2行目以降を辞書として読み込む
            reader = csv.DictReader(text_stream)
            return [row for row in reader]

def sync_master_data_task(db: Session):
    """裏側で動くマスタ同期の本体"""
    try:
        # 1. EDINETコードの同期
        edinet_data = asyncio.run(download_and_parse_csv(EDINET_CODE_URL))
        # ※ ここで SQLAlchemy や bulk_insert等を使って edinet_codes テーブルへ Upsert する処理
        # 例: db.execute("INSERT OR REPLACE INTO edinet_codes ...", parameters)
        
        # 2. ファンドコードの同期
        fund_data = asyncio.run(download_and_parse_csv(FUND_CODE_URL))
        # ※ ここで fund_codes テーブルへ Upsert する処理
        
        db.commit()
        # 成功ログの記録等...
    except Exception as e:
        db.rollback()
        # エラーログの記録...
        print(f"Master Sync Failed: {e}")

@router.post("/run")
async def trigger_master_sync(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _auth = Depends(verify_admin_or_key) # 例のFERNET_KEY認証
):
    """GitHub Actionsから叩かれるエンドポイント"""
    # 時間がかかるのでバックグラウンドに投げてすぐにレスポンスを返す
    background_tasks.add_task(sync_master_data_task, db)
    return {"status": "success", "message": "Master data sync triggered"}
```

この実装であれば、ご提示いただいたGitHub ActionsのYAMLから毎日キックすることで、マスタデータ（企業名やファンド名）が常に最新に保たれます！


# todo 
- [ ] @router.post("/run")は確認必要