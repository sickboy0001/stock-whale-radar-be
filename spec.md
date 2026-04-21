# 要件定義書

## 1. 要件

### 1.1. 非機能要件
- **フレームワーク**: Python 3.11+ / FastAPI / Bootstrap
- **デプロイ**: Google Cloud Run
- **データベース**: SQLite / Turso
- **CI/CD**: GitHub Actions
- **認証**: Google OAuth 2.0 / JWT

### 1.2. 機能要件
- ユーザー認証（サインアップ、ログイン）
- プロフィール管理（メールアドレス、自己紹介）
- バケット管理（注目銘柄のグループ化、並び替え）
- 大量保有報告書の閲覧・検索
- ダッシュボード（最新トレンド、保有変動の可視化）

---

## 2. データベース設計 (SQLite / Turso)

### 2.1. ユーザー・管理系

#### users (ユーザー)
| カラム名 | 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| id | INTEGER | PK, AI | ユーザーID |
| username | TEXT | Unique, Not Null | ユーザー名 |
| email | TEXT | Unique, Not Null | メールアドレス |
| hashed_password | TEXT | Not Null | ハッシュ化済みパスワード |
| bio | TEXT | | 自己紹介 |
| role_type | TEXT | Default 'free' | 権限 (free/paid/highpaid) |
| is_admin | INTEGER | Default 0 | 管理者フラグ (0:一般, 1:管理者) |
| created_at | DATETIME | Default CURRENT_TIMESTAMP | 作成日時 |

#### buckets (バケット)
| カラム名 | 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| id | INTEGER | PK, AI | バケットID |
| user_id | INTEGER | FK (users.id) | 所有ユーザーID |
| name | TEXT | Not Null | バケット名 |
| order_index | INTEGER | Default 0 | 表示順序 |
| created_at | DATETIME | Default CURRENT_TIMESTAMP | 作成日時 |

#### bucket_items (バケット銘柄)
| カラム名 | 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| id | INTEGER | PK, AI | ID |
| bucket_id | INTEGER | FK (buckets.id) | 所属バケットID |
| stock_code | TEXT | Not Null | 証券コード |
| order_index | INTEGER | Default 0 | 表示順序 |

---

### 2.2. マスタデータ

#### edinet_codes (提出者マスタ)
| カラム名 | 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| edinet_code | TEXT | PK | EDINETコード (6桁) |
| submitter_type | TEXT | | 提出者種別 |
| listing_status | TEXT | | 上場区分 |
| consolidated | TEXT | | 連結の有無 |
| capital | INTEGER | | 資本金 |
| settlement_date | TEXT | | 決算日 |
| filer_name | TEXT | Not Null | 提出者名 |
| filer_name_en | TEXT | | 提出者名（英字） |
| filer_name_kana | TEXT | | 提出者名（ヨミ） |
| address | TEXT | | 所在地 |
| industry | TEXT | | 提出者業種 |
| sec_code | TEXT | Index | 証券コード (5桁) |
| jcn | TEXT | | 提出者法人番号 (13桁) |

#### fund_codes (ファンドマスタ)
| カラム名 | 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| fund_code | TEXT | PK | ファンドコード |
| sec_code | TEXT | Index | 証券コード |
| fund_name | TEXT | Not Null | ファンド名 |
| fund_name_kana | TEXT | | ファンド名（ヨミ） |
| security_type | TEXT | | 特定有価証券区分名 |
| period_1 | TEXT | | 特定期1 |
| period_2 | TEXT | | 特定期2 |
| edinet_code | TEXT | FK (edinet_codes.edinet_code) | ＥＤＩＮＥＴコード |
| issuer_name | TEXT | | 発行者名 |

---

### 2.3. 書類・報告書データ

#### documents (書類メタデータ)
| カラム名 | 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| doc_id | TEXT | PK | 書類管理番号 (8桁) |
| seq_number | INTEGER | | ファイル日付ごとの連番 |
| submit_date_time | DATETIME | Index | 提出日時 |
| edinet_code | TEXT | FK (edinet_codes.edinet_code) | 提出者EDINETコード |
| doc_description | TEXT | | 提出書類概要 |
| doc_type_code | TEXT | | 書類種別コード (350等) |
| parent_doc_id | TEXT | | 親書類管理番号 (訂正用) |
| withdrawal_status | INTEGER | Default 0 | 取下区分 (0:通常, 1:取下, 2:被取下) |
| legal_status | INTEGER | | 縦覧区分 (1:縦覧中, 0:期間満了) |

#### substantial_reports (大量保有報告書詳細)
| カラム名 | 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| doc_id | TEXT | PK, FK (documents.doc_id) | 書類管理番号 |
| obligation_date | DATE | Index | 義務発生日 |
| issuer_edinet_code | TEXT | Index | 発行会社EDINETコード |
| issuer_name | TEXT | | 発行者名 |
| holding_ratio | REAL | | 株券等保有割合 (%) |
| prev_holding_ratio | REAL | | 直前の保有割合 (%) |
| holding_purpose | TEXT | | 保有目的 |
| total_number_of_shares | INTEGER | | 保有株券等の数 (総数) |

#### joint_holders (共同保有者)
| カラム名 | 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| id | INTEGER | PK, AI | ID |
| doc_id | TEXT | FK (documents.doc_id) | 書類管理番号 |
| filer_edinet_code | TEXT | | 共同保有者のEDINETコード |
| individual_holding_ratio | REAL | | 各保有者の保有割合 |
| context_ref | TEXT | | XBRL識別子 |

---

## 3. API エンドポイント案

### 3.1. 認証 (Auth)
- `POST /auth/signup`: 新規ユーザー登録
- `POST /auth/login`: ログイン・JWT取得

### 3.2. ユーザー (Users)
- `GET /users/me`: 自身のプロフィール取得
- `PATCH /users/me`: プロフィール更新（メールアドレス、自己紹介）

### 3.3. バケット (Buckets)
- `GET /buckets`: バケット一覧の取得
- `POST /buckets`: 新規バケットの作成
- `PATCH /buckets/{id}`: バケットの名称・表示順序の更新
- `DELETE /buckets/{id}`: バケットの削除
- `GET /buckets/{id}/items`: バケット内銘柄一覧の取得
- `POST /buckets/{id}/items`: バケットへの銘柄追加
- `DELETE /buckets/{id}/items/{stock_code}`: バケットからの銘柄削除

### 3.4. 銘柄・保有情報 (Stocks / Holdings)
- `GET /stocks/dashboard`: ダッシュボード用サマリーデータ
- `GET /stocks/holdings`: 大量保有情報一覧（フィルタ・検索可）
- `GET /stocks/{stock_code}/holdings`: 特定銘柄の保有履歴
- `GET /stocks/{stock_code}/chart`: チャート表示用データ


結論から申し上げますと、その構成は**非常に合理的で、モダンな「スモールスタート向け構成」の正解の一つ**と言えます。

特に、データソースがEDINET（API）であり、定期実行が必要なタスクに対してGitHub Actionsを「実行基盤」として使うのは、コストと管理の手間を最小限に抑える賢い選択です。

構成の妥当性と、検討しておくべきポイントを整理しました。

---


## 4. タスク処理フロー

1.  **GitHub Actions:** `schedule` イベント（cron）で起動。４時間に一回を想定
2.  **Extraction:** Pythonスクリプトを実行し、EDINET APIから書類一覧やXBRLデータを取得。
3.  **Loading:** 取得・加工したデータを、TursoのSDKを使ってDBへ保存。ログもTursoへ記載
    1.  EDINET普通の場合なども、ログへ記載するすること
4.  **Serving:** Cloud Run上のFastAPIが、Tursoのデータを参照してユーザーに表示。

## 3. 実装上の注意点・アドバイス

### ① EDINET APIの制限とリトライ
EDINET APIは時折不安定になったり、接続制限がかかることがあります。
* GitHub Actions側でリトライ処理を組み込むこと。
* 一度に大量のデータを取得しようとすると、GitHub Actionsの実行時間制限（6時間）やメモリ制限に引っかかる可能性があるため、差分更新（前回取得分からの更新）を基本にするのが無難です。

### ② シークレット管理
EDINETのAPIキーやTursoのURL/Tokenは、必ずGitHubの **Settings > Secrets and variables > Actions** に保存し、環境変数として読み込むようにしてください。

