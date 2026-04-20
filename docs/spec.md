# 要件

## 非機能要件

FW:Python+FastAPI
Deploy:CloudRun
DB:SQLite Turso
Trigger:Github Actions

* サインアップ機能をもつこと
* ログイン機能を持つこと
* ログイン者は連絡先のメアドを登録できること。
* ログイン者は自己紹介の登録も可能
* ログインしていないくても「」「」


## 技術詳細

### データベース（SQLite / Turso）設計案
- **users**: id, username, email, hashed_password, bio, created_at
- **buckets**: id, user_id, name, order_index, created_at
- **bucket_items**: id, bucket_id, stock_code, order_index
- **large_holdings**: id, stock_code, reporter_name, share_holding_ratio, change_ratio, report_date, ... (EDINET等からの取得データ)

### API エンドポイント案

#### Auth
- `POST /auth/signup`: 新規登録
- `POST /auth/login`: ログイン・JWT取得

#### Users
- `GET /users/me`: 自身のプロフィール取得
- `PATCH /users/me`: プロフィール更新（メアド、自己紹介）

#### Buckets
- `GET /buckets`: バケット一覧
- `POST /buckets`: バケット作成
- `PATCH /buckets/{id}`: バケット名・順序更新
- `DELETE /buckets/{id}`: バケット削除
- `GET /buckets/{id}/items`: バケット内銘柄一覧
- `POST /buckets/{id}/items`: 銘柄追加
- `DELETE /buckets/{id}/items/{stock_code}`: 銘柄削除

#### Stocks / Holdings
- `GET /stocks/dashboard`: ダッシュボード用サマリー
- `GET /stocks/holdings`: 大量保有情報一覧（フィルタ可）
- `GET /stocks/{stock_code}/holdings`: 特定銘柄の保有履歴
- `GET /stocks/{stock_code}/chart`: チャート用データ
