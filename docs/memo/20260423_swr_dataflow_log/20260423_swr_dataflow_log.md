### 💡 提案：ログ設計の新しい「2本立て」コンセプト

以下の2つのレイヤー（役割）に明確に分ける構成です。

1.  **Job & Task レイヤー（バッチ制御用）**
    *   目的：4時間ごとのバッチがどこまで進んだか、どの `docID` をリトライすべきかを**システム自身が管理するため**のテーブル。
2.  **Event レイヤー（運用・監視・その他の利用）**
    *   目的：人間（開発者）が後からバグの原因を調査したり、ダッシュボードに「今日発生したエラー一覧」や「データの更新履歴」を表示するための**汎用的なログ**テーブル。

このコンセプトに基づくテーブルデザイン案です。

---

### 案1：Job & Task レイヤー（バッチ制御用テーブル）

名前から「import」や「log」を外し、**「ジョブ（全体）」**と**「タスク（個別）」**という名称に変更します。

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

### 🛠️ この「2本立て」によるバッチ処理のイメージ

新しいテーブル構成でバッチを動かすと、Pythonのコードは次のようにスッキリします。

1.  **バッチ開始**: `sync_jobs` に `running` で行を作る。
2.  **API取得**: 未処理の `docID` を `document_tasks` に `pending` として一気に `INSERT` する。
3.  **ループ処理**:
    *   `document_tasks` から `pending` または `failed` (リトライ上限未満) のものをSELECTして処理開始。
    *   処理中、XBRLのタグが見つからないなどの**エラーが発生**！
        ➔ `document_tasks` のステータスを `failed` に更新。
        ➔ 同時に、**`system_events` に `ERROR` レベルで詳細なエラー内容を `INSERT`** する。
    *   **成功**した場合は `document_tasks` を `completed` にする（※あるいは完了したタスクは行ごと `DELETE` してテーブルを軽く保つ運用でもOKです）。
4.  **バッチ終了**: `sync_jobs` を `success` に更新。

---

### まとめ

「バッチ用の状態管理（タスク）」と、「人間が見るための記録（イベントログ）」の役割を分離しました。

*   **タスク管理用**: `sync_jobs` / `document_tasks`
*   **汎用ログ用**: `system_events`

この名前と構成であれば、運用フェーズに入ってからのデバッグや、将来別の機能（例えばLINE通知の送信履歴など）を追加した際にも、柔軟に対応できるはずです。

このテーブル名と「2本立て」の役割分担、しっくりきますでしょうか？