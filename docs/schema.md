


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
| **`ordinance_code`** | TEXT | **【追加】** `ordinanceCode`: 府令コード。**`020`が大量保有関連！** |
| `doc_type_code` | TEXT | `docTypeCode`: 書類種別（`120`=有報, `180`=臨時, `350`=大量保有など） |
| `doc_description` | TEXT | `docDescription`: 「大量保有報告書」「変更報告書」などのテキスト |
| `submitter_edinet_code` | TEXT | `edinetCode`: **【提出者】** クジラ（ファンド等）のEDINETコード |
| `submitter_name` | TEXT | `filerName`: **【提出者】** クジラ（ファンド等）の名称 |
| **`issuer_edinet_code`** | TEXT | **【追加】** `subjectEdinetCode`: **【発行者】** 買われた企業のEDINETコード |
| **`issuer_sec_code`** | TEXT | **【追加】** `subjectSecCode`: **【発行者】** 買われた企業の証券コード |
|issuer_name|TEXT|買われた企業名：トヨタ自動車など|
| `is_withdrawal` | INTEGER | `withdrawalStatus`: 1なら取下げられた書類（無視してOK） |
| `processed_status` | INTEGER | 【独自追加】 解析ステータス (0:未処理, 1:解析成功, 9:エラー) |

#### 1. 「提出者」と「発行者」が逆転する
有価証券報告書（決算書）の場合、「提出者＝その企業自身」です。
しかし、**大量保有報告書の場合、「提出者＝クジラ（ファンド）」であり、「発行者（subject）＝買われた企業」**になります。
そのため、APIレスポンスに含まれる `subjectEdinetCode`（誰の株を買ったか）を保存するカラムを絶対に分ける必要がありました。

#### 2. `ordinanceCode` を保存しておく
APIを取得した時点のバッチ処理で「020」だけを弾き出しても良いですが、メタデータとして保存しておけば、後から「Tursoの中で、大量保有報告書だけを数えたい」といった際に、`WHERE ordinance_code = '020'` とするだけで一発で検索できます。

#### 3. 証券コードの罠（末尾のゼロ）
EDINET APIから返ってくる証券コード（`subjectSecCode`）は、**実は「5桁」**です。（例：トヨタ自動車の場合 `7203` ではなく `72030` と返ってきます。末尾に必ずゼロが付きます）。
このまま画面（フロントエンド）に出すと投資家は違和感を覚えるため、APIから取得してTursoに入れる際、あるいはフロントエンドで表示する際に、`[0:4]` で4桁にスライスする処理を忘れないようにしてください。



#### `ownership_reports` テーブル（大量保有・変更：`ordinanceCode = 020`）
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

財務数値の主要項目を格納します。XBRLから数値のみを抽出してフラットに持たせます。

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
臨時報告書は定型的な数値が少ないため、提出理由などのテキスト情報を中心に持ちます。

| カラム名 | 型 | 説明 |
| :--- | :--- | :--- |
| `id` | INTEGER (PK) | サロゲートキー |
| `docID` | TEXT (FK) | `documents.docID` |
| `reason_code` | TEXT | 提出理由（代表取締役の異動、新株発行など） |
| `description` | TEXT | 具体的な内容（テキストサマリー） |

#### ⑤ `joint_holders` テーブル（共同保有者内訳）

「グループ合計の7%ではなく、内訳のファンドBが3%持っているという情報まで正確に抜き出したい」という目的がある場合に利用するテーブル

例えば「エフィッシモ」が提出者で、内部で「ファンドAが3%」「ファンドBが2%」持っている場合の内訳を保存します。

| カラム名 | 型 | 説明 |
| :--- | :--- | :--- |
| `id` | INTEGER (PK) | サロゲートキー |
| `doc_id` | TEXT (FK) | `documents.doc_id` と紐付け |
| `holder_name` | TEXT | 共同保有者の名前（〇〇ファンド等） |
| `holding_ratio` | REAL | その共同保有者が単体で持っている割合(%) |

* `is_joint_holding`: **1 (True)** の場合の動き

*   **⚠️ 個人開発における注意点:**
    共同保有者のXBRL解析は、構造が入れ子（配列）になっているため、単独の保有割合を抜くよりも**パースの難易度が一段階上がります。**
    そのため、システム開発のロードマップとしては**「まずは共同保有者を無視して、②の合計割合（グループ全体で何％か）だけを完璧に取得する」**ことをMVP（初期リリース）の目標とし、この `joint_holders` テーブルのデータ投入は第2フェーズ（アップデート）に回すのがおすすめです。



#### ⑥ `edinet_codes` テーブル（EDINETコードマスタ）
買われた企業（発行者）の名前や、企業型の提出者の情報を引くために使います。

```sql
CREATE TABLE edinet_codes (
  edinet_code TEXT PRIMARY KEY,       -- 例: E00004
  submitter_type TEXT,                -- 提出者種別 (例: 内国法人・組合)
  listed_category TEXT,               -- 上場区分 (例: 上場)
  is_consolidated TEXT,               -- 連結の有無 (有/無)
  capital INTEGER,                    -- 資本金 (百万円)
  fiscal_year_end TEXT,               -- 決算日 (例: 5月31日)
  submitter_name TEXT NOT NULL,       -- 提出者名 (例: カネコ種苗株式会社) ※これが企業名になる！
  submitter_name_en TEXT,             -- 提出者名（英字）
  submitter_name_kana TEXT,           -- 提出者名（ヨミ）
  address TEXT,                       -- 所在地
  industry TEXT,                      -- 提出者業種 (例: 水産・農林業)
  sec_code TEXT,                      -- 証券コード (例: 13760 ※末尾0の5桁)
  corporate_number TEXT               -- 提出者法人番号
);
```

#### ⑦ `fund_codes` テーブル（ファンドコードマスタ）
投資信託などのファンド名を引くために使います。（提出者がファンドの場合に利用）

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



#### ① `sync_jobs`（旧: import_runs）
「同期バッチ処理」の1回分の実行履歴です。

```sql
CREATE TABLE sync_jobs (
  job_id            TEXT PRIMARY KEY,        -- 例: 'job_20260421_1200' または UUID
  job_type          TEXT NOT NULL,           -- 'edinet_daily_sync' など (将来別のバッチが増えた時用)
  started_at        DATETIME NOT NULL,
  finished_at       DATETIME,
  status            TEXT NOT NULL,           -- 'running', 'success', 'failed'
  total_docs_found  INTEGER DEFAULT 0,       -- APIで見つけた総数
  target_docs_count INTEGER DEFAULT 0,       -- 処理対象(060)の数
  success_count     INTEGER DEFAULT 0,
  error_count       INTEGER DEFAULT 0
);
```

#### ② `document_tasks`（旧: import_document_logs）
ドキュメント1件ごとの「処理キュー（タスク）」です。これはログとして残し続けるのではなく、**「未処理・エラーのものを管理する」のが主目的**です。

```sql
CREATE TABLE document_tasks (
  doc_id           TEXT PRIMARY KEY,
  job_id           TEXT NOT NULL,
  status           TEXT NOT NULL,            -- 'pending'(待機), 'processing'(処理中), 'completed'(完了), 'failed'(失敗)
  retry_count      INTEGER DEFAULT 0,
  next_retry_at    DATETIME,                 -- 次回いつ再実行するか（バックオフ制御用）
  updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (job_id) REFERENCES sync_jobs(job_id)
);
```
*   **名前の変更意図**: 「ログ」ではなく「タスク」と呼ぶことで、「ステータスを更新して処理を進めるもの」という役割が明確になります。

---

### 案2：Event レイヤー（ほかに利用できる汎用ログ）

もう一つの柱として、**「何でも放り込める汎用イベントログ」**を用意します。
バッチのエラーだけでなく、将来的にフロントエンド（Next.js）からのエラーや、特定のユーザーの検索履歴なども入れられる設計です。

#### ③ `system_events`（汎用ログ・監査用）

```sql
CREATE TABLE system_events (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  event_level      TEXT NOT NULL,            -- 'INFO', 'WARN', 'ERROR', 'FATAL'
  event_category   TEXT NOT NULL,            -- 'batch_sync', 'xbrl_parse', 'api_fetch', 'system' など
  doc_id           TEXT,                     -- 関連する書類があれば入れる (NULL可)
  message          TEXT NOT NULL,            -- "パースに失敗しました", "APIレートリミット到達" など
  error_details    TEXT,                     -- スタックトレースや生のエラーJSONを入れる（TEXT型でJSONを格納）
  created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

*   **このテーブルの強み**:
    「Tursoでエラーになった `doc_id` の詳細が見たい」という場合、この `system_events` を `WHERE event_level = 'ERROR'` で検索するだけで、詳細なスタックトレースや原因（例：XBRLのタグが想定と違った、など）を後からゆっくり分析できます。



---



EDINETコードとファンドコードのCSVリストをご提示いただき、ありがとうございます！

これらのCSVをデータベース（Turso）にマスタとして取り込むアプローチは、**「Stock Whale Radar」を完璧なシステムにするための最後のピース**です。

APIのレスポンスには含まれない「対象企業名（買われた会社の名前）」を、このマスタから引っ張ってくる（名前解決する）ことで、フロントエンドでの表示が圧倒的に分かりやすくなります。

ご提示いただいたCSVのデータ構造に基づき、**マスタテーブルのSchema（スキーマ）定義**と、**それを利用したバッチ処理のアップデート案**をまとめました。

（※なお、ご提示いただいたテキスト内に、以前のやり取りで誤っていた `ordinanceCode = 020` という記述が残っていましたが、**大量保有の正解は `060`** ですので、以下の定義では `060` に修正して統合しています。）

---

### 1. 追加するマスタテーブルのスキーマ定義

提供いただいたCSVをTurso（SQLite）に格納するためのテーブル定義です。

---

### 2. インポート処理（名前解決）のアップデート

マスタテーブルができたことで、バッチ処理の中で以下のように「企業名」を補完（名前解決）して `documents` テーブルに保存できるようになります。

**▼ Pythonバッチ処理のイメージ**
```python
# APIから取得したメタデータ
api_doc = {
    "docID": "S1001234",
    "submitterName": "エフィッシモ・キャピタル", 
    "subjectEdinetCode": "E00004", # カネコ種苗のコード
    "subjectSecCode": "13760"      # カネコ種苗の証券コード
}

# 1. Tursoの edinet_codes マスタから、対象企業名を検索する
# SQL: SELECT submitter_name FROM edinet_codes WHERE edinet_code = 'E00004'
issuer_name = fetch_company_name_from_db(api_doc['subjectEdinetCode']) 
# 結果: "カネコ種苗株式会社"

# 2. 証券コードの末尾の「0」をカットして4桁にする
sec_code_4digit = api_doc['subjectSecCode'][:4] 
# 結果: "1376"

# 3. 綺麗になったデータを documents テーブルに INSERT する
insert_into_documents(
    doc_id = api_doc['docID'],
    issuer_sec_code = sec_code_4digit, # 4桁にした証券コード
    issuer_name = issuer_name,         # マスタから引いた企業名！
    # ...その他の項目...
)
```
この処理を挟むことで、`documents` テーブルを見るだけで「エフィッシモがカネコ種苗（1376）を買った」ということが完全にわかるようになります。

---

### 3. 全体スキーマ（テーブル構成）の最終決定版

これまでの議論（FSMによるログ設計、マスタデータ、不要なテーブルの排除）をすべて統合した、**Stock Whale Radarの「最終データベース構成」**です。


#### 【トランザクション系（メインデータ）】
*   **`documents`**: 書類の外箱メタデータ。
    *   ※ `ordinance_code` (`060`=大量保有関連) を保持。
    *   ※ APIから取得後、マスタを参照して `issuer_name`（買われた企業名）を埋めてから保存。
*   **`ownership_reports`**: 大量保有の事実データ。
    *   ※ `doc_id` で `documents` と1:1で紐づく。
    *   ※ `obligation_date` (義務発生日)、`holding_ratio` (保有割合)、`prev_holding_ratio` (前回割合) を保存。
*   **`joint_holders`** (※将来拡張用): 共同保有者の内訳データ。

---


#### ログレイヤー

新しいテーブル構成でバッチを動かすと、Pythonのコードは次のようにスッキリします。

*   **タスク管理用**: `sync_jobs` / `document_tasks`
*   **汎用ログ用**: `system_events`

1.  **バッチ開始**: `sync_jobs` に `running` で行を作る。
2.  **API取得**: 未処理の `docID` を `document_tasks` に `pending` として一気に `INSERT` する。
3.  **ループ処理**:
    *   `document_tasks` から `pending` または `failed` (リトライ上限未満) のものをSELECTして処理開始。
    *   処理中、XBRLのタグが見つからないなどの**エラーが発生**！
        ➔ `document_tasks` のステータスを `failed` に更新。
        ➔ 同時に、**`system_events` に `ERROR` レベルで詳細なエラー内容を `INSERT`** する。
    *   **成功**した場合は `document_tasks` を `completed` にする（※あるいは完了したタスクは行ごと `DELETE` してテーブルを軽く保つ運用でもOKです）。
4.  **バッチ終了**: `sync_jobs` を `success` に更新。

