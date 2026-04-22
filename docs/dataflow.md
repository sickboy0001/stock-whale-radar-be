
# 🚀 Stock Whale Radar インポート・データフロー仕様書

## 1. インポートの流れ（4時間に1回のルーチン）

1.  **Fetch List:** EDINETの「書類一覧API」を叩き、本日の全 `docID` メタデータ（JSON）を取得する。
2.  **Filter:** Tursoの `documents` テーブルと照合し、以下の条件を**すべて満たすもの**だけを抽出する。
    *   Tursoに未登録の `docID` であること。
    *   APIレスポンスの **`ordinanceCode` が `060`（株券等の大量保有の状況の開示に関する内閣府令）** であること。
3.  **Analyze:** 対象の `docID` についてXBRLファイル（ZIP）をダウンロードし、Pythonパーサーに渡して中身（義務発生日、保有割合など）を抽出する。
4.  **Transaction (Tursoへ保存):**
    *   `documents` テーブルにメタデータを保存。
    *   `ownership_reports` テーブルに解析結果（誰が・どこを・何％）を保存。
    *   ※もしAPIメタデータで「訂正フラグ」が立っている書類であれば、過去の同一提出者・同一銘柄のレコードの有効フラグを `0` にし、最新を `1` にする論理更新を行う。

---

## 2. データフロー詳細

#### ① データ取得（Fetch Phase）
*   **トリガー:** 4時間に1回のスケジューラ（Cloud Scheduler等）。
*   **アクション:** Cloud Run Jobs（Python）を起動し、EDINET APIからメタデータを取得。

#### ② フィルタリング（Routing Phase）
今回は「大量保有」に一点突破するため、複雑な分岐は不要です。`ordinanceCode` だけで安全にフィルタリングします。

```python
# Pythonでのフィルタリング・イメージ

document_list = get_edinet_list() # 当日のリスト取得

for doc in document_list:
    # 府令コードが「060（大量保有関連）」のものだけを抽出！
    if doc['ordinanceCode'] == '060':
        # これで「大量保有報告書」「変更報告書」「訂正報告書」を漏れなくキャッチできる
        parse_ownership_report(doc['docID'])
    else:
        # 060以外（決算書など）は今回はすべて無視！
        pass
```

#### ③ 構造化解析（Parsing Phase）
*   **XBRL解析:** ダウンロードしたZIPから `.xbrl` ファイルを展開し、特定のタグから値を抽出。
    *   `<jpcrp_cor:ProportionOfSharesHeld...>` ➔ 今回の保有割合
    *   `<jpcrp_cor:ProportionOfSharesHeldInPreviousReport...>` ➔ 前回の保有割合
    *   `<jpcrp_cor:DateOnWhichDutyToReportArose...>` ➔ 報告義務発生日

#### ④ データベース書き込み（Upsert Phase）
Tursoへの書き込みはトランザクション（アトミック）に行います。
*   **親テーブル:** `documents` にレコード作成（APIのメタデータ）。
*   **子テーブル:** `ownership_reports` に解析結果を格納。

---

## 3. この設計の強み

1.  **冪等性（べきとうせい）の確保:**
    何度実行しても、`docID` が一意であればデータが重複しません。途中でXBRL解析エラーが起きても「未処理の `docID`」から再開するだけで済みます。
2.  **ストレージと開発コストの極小化:**
    決算書や臨時報告書を切り捨て、`060`（大量保有）に絞ったことで、**Pythonのパーサー開発が1種類だけで済みます。** また、Tursoのストレージ容量も劇的に節約でき、無料枠での運用が極めて現実的になります。
    MVPとしては切り捨てますが、テーブルスペースなどは準備しておきます。
3.  **リアルタイム性と検索の高速化:**
    4時間おきの実行で最新の大株主の動きをキャッチし、Turso（エッジDB）の速さを活かしてフロントエンド（Next.js）で「急上昇ランキング」などを爆速で表示できます。


## 例
### 証券コードに対して大量に取得しているファンドの一覧
```SQL
SELECT 
    d.submitter_name AS 'クジラ（ファンド名）',
    o.holding_ratio AS '現在の保有割合',
    o.obligation_date AS '最終アクション日'
FROM documents d
JOIN ownership_reports o ON d.doc_id = o.doc_id
WHERE d.issuer_sec_code = '9984' -- 探したい証券コード（例：ソフトバンク）
  AND o.holding_ratio >= 5.0    -- 5%以上持っている
  AND o.processed_status = 1    -- 有効な最新データ
ORDER BY o.holding_ratio DESC;  -- 割合が多い順
```

###　ファンド固定で、どの程度の証券を持っているか

```SQL
WITH RankedReports AS (
    SELECT 
        d.issuer_sec_code AS sec_code,         -- 証券コード
        d.issuer_name AS company_name,         -- 企業名（※後述）
        o.holding_ratio AS current_ratio,      -- 保有割合
        o.prev_holding_ratio AS prev_ratio,    -- 前回割合
        o.obligation_date AS action_date,      -- 最終アクション日
        -- ↓ここが魔法の呪文：「銘柄ごとに、発生日が新しい順に1,2,3...と番号を振る」
        ROW_NUMBER() OVER (
            PARTITION BY d.issuer_sec_code 
            ORDER BY o.obligation_date DESC
        ) as row_num
    FROM documents d
    JOIN ownership_reports o ON d.doc_id = o.doc_id
    WHERE d.submitter_name LIKE '%エフィッシモ%' -- 検索したいファンド名（または edinet_code）
)
SELECT 
    sec_code AS '証券コード',
    company_name AS '対象企業',
    current_ratio AS '現在の保有割合(%)',
    ROUND(current_ratio - prev_ratio, 2) AS '増減',
    action_date AS '最終更新日'
FROM RankedReports
WHERE row_num = 1      -- 最新の1件（row_numが1のもの）だけを抽出！
  AND current_ratio >= 5.0 -- ※5%以上保有しているものだけを残す（後述）
ORDER BY current_ratio DESC; -- 保有割合が多い順に並べる

```

* **🛠️ 設計のワンポイントアドバイス**
* 1. documents テーブルに「対象企業名」を追加
  * 前回のテーブル設計で1点だけ補足させてください。
  * documents テーブルに証券コード（issuer_sec_code）は入れましたが、**issuer_name（買われた企業名：トヨタ自動車など）**というカラムも追加しておくことを強くお勧めします。（EDINET APIの subjectName から取得できます）
  * これがないと、画面に表示する際に「証券コード➔企業名」の変換マスタを別途用意する手間が増えてしまいます。
* 2. 「5%未満（報告義務消失）」の扱い
  * 大口投資家は株を売り抜けて**「5%未満」**になった場合、「5%未満になりましたよ」という最後の変更報告書を出します（これで報告義務が消失し、表舞台から消えます）。
  * 上記のSQLの最後の部分で AND current_ratio >= 5.0 としているのは、「過去に持っていたけど、すでに5%未満に売り抜けて逃げた銘柄」をリストから除外するためです。


とてもよく整理された仕様だと思います 👍  
その前提を崩さずに、

*   ✅ **別途 Turso に「処理ログ」を残す目的**
*   ✅ **冪等性・再実行耐性・デバッグ容易性**
*   ✅ **将来の拡張（失敗検知 / 再処理 / 監視）**

を満たす形で、**現実的かつ過不足ないログ設計案**をまとめます。

***

# ✅ 結論サマリ（先に全体像）

### ログは「2レイヤー」で考えるのがベスト

| レイヤー        | テーブル                   | 役割                  |
| ----------- | ---------------------- | ------------------- |
| **Run単位ログ** | `import_runs`          | 4時間に1回の「バッチ全体」の状態   |
| **Doc単位ログ** | `import_document_logs` | 各 `docID` がどこまで進んだか |

👉  
**documents / ownership\_reports は「正規データ」**  
**logs は「状態管理・監査・再実行のためのDB内ジョブキュー」**

という役割分離が肝です。

***

# 1️⃣ import\_runs（バッチ実行ログ）

## 目的

*   「この4時間ジョブは成功した？」を一瞬で把握
*   障害時に **どのRunに紐づく失敗か** を追える
*   将来 Cloud Monitoring / Slack通知につなげやすい

## テーブル案

```sql
CREATE TABLE import_runs (
  run_id            TEXT PRIMARY KEY,      -- UUID
  started_at        DATETIME NOT NULL,
  finished_at       DATETIME,
  status            TEXT NOT NULL,           -- running / success / failed
  total_docs        INTEGER,                 -- EDINETから取得した総数
  target_docs       INTEGER,                 -- ordinanceCode=060 & 未登録
  success_docs      INTEGER,
  failed_docs       INTEGER,
  error_message     TEXT                     -- Run全体の致命的エラー
);
```

## 登録タイミング定義

| タイミング   | 処理                                              |
| ------- | ----------------------------------------------- |
| ジョブ開始   | `INSERT (run_id, started_at, status='running')` |
| Fetch後  | `UPDATE total_docs, target_docs`                |
| 全doc完了  | `UPDATE finished_at, status='success'`          |
| 途中クラッシュ | `status='failed', error_message`                |

✅ **Runは必ず1行できる** → 観測性が爆上がりします。

***

# 2️⃣ import\_document\_logs（docID単位ログ）

## 目的（ここが一番重要）

*   ✅ docIDごとの **進捗トラッキング**
*   ✅ **途中失敗 → 再実行時のリトライ制御**
*   ✅ XBRLパース失敗・仕様変更の検知
*   ✅ 「documentはあるが ownership が無い」事故防止

***

## テーブル案（実戦仕様）

```sql
CREATE TABLE import_document_logs (
  doc_id           TEXT PRIMARY KEY,
  run_id           TEXT NOT NULL,
  ordinance_code   TEXT,
  status           TEXT NOT NULL,
  -- fetched / filtered / parsed / persisted / skipped / failed

  error_stage      TEXT,      -- fetch | parse | save
  error_message    TEXT,

  retries          INTEGER DEFAULT 0,
  created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### status は有限状態機械（FSM）として扱う

    fetched
       ↓
    filtered (060 & 未登録)
       ↓
    parsed
       ↓
    persisted ✅

失敗系：

    failed (error_stage=parse)
    failed (error_stage=save)

***

## docIDログの登録 & 更新タイミング

### ✅ 強く推奨する順序

#### ① Filter合格時（docIDを“掴んだ瞬間”）

```sql
INSERT INTO import_document_logs
(doc_id, run_id, ordinance_code, status)
VALUES (?, ?, '060', 'filtered');
```

👉  
**ここで記録する理由**  
→ XBRL取得前に落ちても「未処理docID」が可視化される

***

#### ② XBRL解析成功時

```sql
UPDATE import_document_logs
SET status = 'parsed',
    updated_at = CURRENT_TIMESTAMP
WHERE doc_id = ?;
```

***

#### ③ Turso保存成功（トランザクションcommit後）

```sql
UPDATE import_document_logs
SET status = 'persisted',
    updated_at = CURRENT_TIMESTAMP
WHERE doc_id = ?;
```

✅  
**documents / ownership\_reports が揃って初めて persisted**

***

#### ④ 失敗時（どの段でも）

```sql
UPDATE import_document_logs
SET status = 'failed',
    error_stage = 'parse',
    error_message = ?,
    retries = retries + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE doc_id = ?;
```

***

# 3️⃣ documents / ownership\_reports との責務分離

とても良い設計なので、こう整理できます：

| テーブル                   | 意味                       |
| ---------------------- | ------------------------ |
| `documents`            | EDINET書類の**正規マスタ**       |
| `ownership_reports`    | 大量保有の**事実データ**           |
| `import_document_logs` | 「このdocIDは**どこまで処理できたか**」 |

👉  
**「documentsがある ≠ 正常完了」問題をログで防止**

***

# 4️⃣ 冪等性 & 再実行戦略（重要）

### 再実行時のSELECT条件例

```sql
SELECT doc_id
FROM import_document_logs
WHERE status IN ('filtered', 'failed')
  AND retries < 3;
```

✅

*   EDINET APIは再取得不要
*   「XBRLが一時壊れていた」「一時的障害」に耐性あり

***

# 5️⃣ 訂正報告書（無効化更新）との関係

あなたの設計は正しいです。

**ログ側ではこう扱うのがベスト：**

*   訂正かどうか → `documents.is_correction`
*   論理無効化処理は **ownership\_reports の責務**
*   ログは **単に persisted になっていれば OK**

👉  
**「訂正で何件無効化されたか」は将来メטרicsで追加可能**

***

# 6️⃣ 最小構成（MVP）ならこう削れる

もし「まずは最小で」とするなら：

*   `import_runs` → **後回しOK**
*   `import_document_logs` → **必須**

理由：

*   docID単位ログがないと **再実行の自動化が困難**
*   Cloud Run のstdoutログだけでは **DB状態と乖離** する

***

# ✅ 最後に：この設計の評価

正直に言って、

*   ✅ フィルタ戦略（ordinanceCode=060）
*   ✅ docID基準の冪等設計
*   ✅ 4時間バッチ × Edge DB
*   ✅ SQLのユースケース設計

どれも **「本番で壊れない」設計**です。

ログをこの形で足すと、

