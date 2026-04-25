# データベース設計 (Stock Whale Radar)

---

## 1. `docID` 基準の取得における注意点

実は、`docID`（例：S100XXXX）の連番は、必ずしも**「公開された順番」や「時系列」と完全に一致しない**場合があります。


### ① 履歴テーブル（Transaction Table）
すべての `docID` をそのまま保存します。ただし、「訂正」があった場合のみ、元データのフラグを「無効」にします。

| docID | 日付 | 種別 | 保有割合 | 状態フラグ |
| :--- | :--- | :--- | :--- | :--- |
| S100123 | 4/1 | 190 | 5.1% | **無効（訂正されたため）** |
| S100456 | 4/10 | 200 | 6.2% | 有効 |
| S100789 | 4/1 | 210 | **5.2%** | **有効（S100123の正しい姿）** |

### ② 最新状況テーブル（Master Table）
「提出者×銘柄」で1行にまとめ、常に最新の報告書の内容で上書きします。

| 提出者 | 銘柄 | 最新保有割合 | 最終更新docID |
| :--- | :--- | :--- | :--- |
| 山田太郎 | 9999 | 6.2% | S100456 |

---

Turso（SQLiteベースの分散型データベース）に構造化した状態でデータを落とし込む設計ですね。
結論から言うと、**「`docID` の最大値を基準にする」という戦略は、EDINET APIの仕様上、少し注意が必要なポイントがあります。**

非常に効率的なアプローチですが、データの抜け漏れを防ぐための現実的なワークフローを整理しました。

* **欠番や逆転のリスク:** 内部処理の都合で番号が前後したり、提出はされたが公開までにタイムラグがあるケースがあります。
* **「提出日」ベースの取得が定石:** EDINET API（書類一覧API）は「年月日」を指定して取得する仕様です。

### 推奨される取得ロジック
「4時間に1回」のバッチであれば、以下の流れが最も確実です。

1.  **当日分を丸ごと取得:** APIで「今日（`date=YYYY-MM-DD`）」の書類一覧を全件取得。
2.  **差分比較:** 取得したリストの中で、**自社DB（Turso）に存在しない `docID` だけ**を抽出して、XBRL解析・インポートに回す。
3.  **前日分の最終確認:** 夜間のバッチ等で、念のため「昨日分」も再スキャンして、遅れて登録されたものがないかチェックする。

---

## 2. Tursoでのデータベース構造（テーブル設計案）

Tursoの特性（エッジでの高速読み取り）を活かしつつ、大量保有報告書を構造化するなら、以下のようなテーブル構成が理想的です。

### 修正版：① `documents` テーブル（共通メタデータ）

| カラム名（物理名） | 型 (SQLite) | APIのキー名 / 説明 |
| :--- | :--- | :--- |
| `doc_id` | TEXT (PK) | `docID`: 書類管理番号（例: S100XXXX） |
| `submit_datetime` | DATETIME | `submitDateTime`: 提出日時 |
| **`ordinance_code`** | TEXT | `ordinanceCode`: 府令コード |
| `form_code` | TEXT | `formCode`: 様式コード |
| `doc_type_code` | TEXT | `docTypeCode`: 書類種別（`120`=有報, `180`=臨時, `350`=大量保有など） |
| `doc_description` | TEXT | `docDescription`: 提出書類概要 |
| `submitter_edinet_code` | TEXT | `edinetCode`: 提出者のEDINETコード |
| `submitter_name` | TEXT | `filerName`: 提出者の名称 |
| `sec_code` | TEXT | `secCode`: 提出者の証券コード (5桁) |
| `jcn` | TEXT | `JCN`: 提出者の法人番号 |
| `fund_code` | TEXT | `fundCode`: ファンドコード |
| **`issuer_edinet_code`** | TEXT | `issuerEdinetCode`: **【発行者】** 大量保有報告書等の場合の発行会社EDINETコード |
| **`subject_edinet_code`** | TEXT | `subjectEdinetCode`: **【対象者】** 公開買付報告書等の場合の対象EDINETコード |
| `issuer_name` | TEXT | 解析時にマスタから解決した企業名 |
| `withdrawal_status` | INTEGER | `withdrawalStatus`: 取下区分 (0:通常, 1:取下書, 2:取下げられた書類) |
| `doc_info_edit_status` | INTEGER | `docInfoEditStatus`: 書類情報修正区分 (0:通常, 1:修正情報, 2:修正された書類) |
| `disclosure_status` | INTEGER | `disclosureStatus`: 開示不開示区分 |
| `xbrl_flag` | INTEGER | `xbrlFlag`: XBRL有無フラグ |
| `pdf_flag` | INTEGER | `pdfFlag`: PDF有無フラグ |
| `csv_flag` | INTEGER | `csvFlag`: CSV有無フラグ |
| `legal_status` | INTEGER | `legalStatus`: 縦覧区分 |
| `processed_status` | INTEGER | 【独自追加】 解析ステータス (0:未処理, 1:解析成功, 9:エラー) |

#### 1. API v2 のレスポンス項目を網羅
EDINET API v2 の書類一覧APIから返却される `results` 配列の主要な項目をすべて格納できるように設計を拡張しました。

#### 2. 取下・修正フラグの管理
`withdrawalStatus` や `docInfoEditStatus` を保持することで、APIの仕様に従い「どの書類が有効か」を正確に判定できます。

#### 3. 証券コードの末尾のゼロ
EDINET APIから返ってくる証券コードは末尾に必ずゼロが付く5桁です。解析時に必要に応じて4桁にスライスします。

### ② 解析済み個別テーブル

#### `ownership_reports` テーブル（大量保有・変更：`ordinanceCode = 060`）
前述の保有割合などのデータを格納します。
大口投資家の保有状況を格納する、このシステムの**心臓部**です。
投資家にとって「いつ株を買った/売ったのか」という**「報告義務発生日」**が非常に重要になるため、カラムを追加しました。（※「提出日」とは数日ズレるためです）

| カラム名 (物理名) | 型 (SQLite) | 説明 |
| :--- | :--- | :--- |
| `id` | INTEGER (PK) | サロゲートキー（Auto Increment） |
| `doc_id` | TEXT (FK) | `documents.doc_id` と紐付け |
| **`obligation_date`** | DATE | **【追加】 報告義務発生日（株が動いたXデー）** |
| `holding_ratio` | REAL | 今回の保有割合（%） |
| `prev_holding_ratio` | REAL | 前回の保有割合（%） |
| `holding_purpose` | TEXT | 保有目的（純投資、経営への助言など） |
| `is_joint_holding` | INTEGER | 共同保有者の有無 (0: 無し, 1: 有り) |

*   **開発のヒント:** XBRLの中から `<jpcrp_cor:ProportionOfSharesHeld...>` などのタグを探して割合（REAL型）をパースします。

### ③ `financial_summaries` テーブル（有報・四半期：120, 140系）

| カラム名 | 型 | 説明 |
| :--- | :--- | :--- |
| `id` | INTEGER (PK) | サロゲートキー |
| `docID` | TEXT (FK) | `documents.docID` |
| `period_start` | DATE | 自（会計期間開始日） |
| `period_end` | DATE | 至（会計期間終了日） |
| `net_sales` | INTEGER | 売上高/営業収益 |
| `operating_income` | INTEGER | 営業利益 |
| `net_income` | INTEGER | 当期純利益 |
| `net_assets` | INTEGER | 純資産額 |
| `total_assets` | INTEGER | 総資産額 |

### ④ `extraordinary_reports` テーブル（臨時報告書：180系）

| カラム名 | 型 | 説明 |
| :--- | :--- | :--- |
| `id` | INTEGER (PK) | サロゲートキー |
| `docID` | TEXT (FK) | `documents.docID` |
| `reason_code` | TEXT | 提出理由（代表取締役の異動、新株発行など） |
| `description` | TEXT | 具体的な内容（テキストサマリー） |

#### ⑤ `joint_holders` テーブル（共同保有者内訳）

| カラム名 | 型 | 説明 |
| :--- | :--- | :--- |
| `id` | INTEGER (PK) | サロゲートキー |
| `doc_id` | TEXT (FK) | `documents.doc_id` と紐付け |
| `holder_name` | TEXT | 共同保有者の名前（〇〇ファンド等） |
| `holding_ratio` | REAL | その共同保有者が単体で持っている割合(%) |

---

#### ⑥ `edinet_codes` テーブル（EDINETコードマスタ）

```sql
CREATE TABLE edinet_codes (
  edinet_code TEXT PRIMARY KEY,       -- 例: E00004
  submitter_type TEXT,                -- 提出者種別 (例: 内国法人・組合)
  listed_category TEXT,               -- 上場区分 (例: 上場)
  is_consolidated TEXT,               -- 連結の有無 (有/無)
  capital INTEGER,                    -- 資本金 (百万円)
  fiscal_year_end TEXT,               -- 決算日 (例: 5月31日)
  submitter_name TEXT NOT NULL,       -- 提出者名 (例: カネコ種苗株式会社)
  submitter_name_en TEXT,             -- 提出者名（英字）
  submitter_name_kana TEXT,           -- 提出者名（ヨミ）
  address TEXT,                       -- 所在地
  industry TEXT,                      -- 提出者業種 (例: 水産・農林業)
  sec_code TEXT,                      -- 証券コード (例: 13760 ※末尾0の5桁)
  corporate_number TEXT               -- 提出者法人番号
);
```

#### ⑦ `fund_codes` テーブル（ファンドコードマスタ）

```sql
CREATE TABLE fund_codes (
  fund_code TEXT PRIMARY KEY,         -- 例: G01003
  sec_code TEXT,                      -- 証券コード (ファンド自体が上場している場合)
  fund_name TEXT NOT NULL,            -- ファンド名 (例: しんきんインデックスファンド２２５)
  fund_name_kana TEXT,                -- ファンド名（ヨミ）
  category TEXT,                      -- 特定有価証券区分名
  specific_period1 TEXT,              -- 特定期1
  specific_period2 TEXT,              -- 特定期2
  edinet_code TEXT,                   -- 紐づくEDINETコード (運用会社のコード)
  issuer_name TEXT                    -- 発行者名 (例: しんきんアセットマネジメント投信株式会社)
);
```

---

#### ① `sync_jobs`

```sql
CREATE TABLE sync_jobs (
  job_id            TEXT PRIMARY KEY,
  job_type          TEXT NOT NULL,
  started_at        DATETIME NOT NULL,
  finished_at       DATETIME,
  status            TEXT NOT NULL,           -- 'running', 'success', 'failed'
  total_docs_found  INTEGER DEFAULT 0,
  target_docs_count INTEGER DEFAULT 0,
  success_count     INTEGER DEFAULT 0,
  error_count       INTEGER DEFAULT 0
);
```

#### ② `document_tasks`

```sql
CREATE TABLE document_tasks (
  doc_id           TEXT PRIMARY KEY,
  job_id           TEXT NOT NULL,
  status           TEXT NOT NULL,            -- 'pending', 'processing', 'completed', 'failed'
  retry_count      INTEGER DEFAULT 0,
  next_retry_at    DATETIME,
  updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (job_id) REFERENCES sync_jobs(job_id)
);
```

#### ③ `system_events`

```sql
CREATE TABLE system_events (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  event_level      TEXT NOT NULL,
  event_category   TEXT NOT NULL,
  doc_id           TEXT,
  message          TEXT NOT NULL,
  error_details    TEXT,
  created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### ④ `import_daily_status`

```sql
CREATE TABLE import_daily_status (
  target_date       TEXT PRIMARY KEY,
  status            TEXT NOT NULL,           -- 'pending', 'processing', 'completed', 'failed'
  total_docs_count  INTEGER DEFAULT 0,
  target_docs_count INTEGER DEFAULT 0,
  success_count     INTEGER DEFAULT 0,
  last_run_start_at DATETIME,
  last_run_end_at   DATETIME,
  error_message     TEXT
);
```
