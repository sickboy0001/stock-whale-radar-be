# Stock Whale Radar Backend (BE)

## プロジェクト概要
「大量保有報告書」などのデータを解析し、大口投資家（クジラ）の動きを可視化・追跡するためのバックエンドサービスです。

## 主な機能
- **ユーザー認証**: サインアップ、ログイン機能。
- **プロフィール管理**: メールアドレス、自己紹介の登録。
- **バケット管理**: 注目銘柄を「バケット」としてグループ化して管理。
- **大量保有情報閲覧**: 最新の大口保有データの表示、特定銘柄の履歴追跡。
- **ダッシュボード**: 保有数の変動が大きい銘柄や、最新のトレンドをサマリー表示。

## 技術スタック
- **言語/フレームワーク**: Python 3.11+ / FastAPI
- **データベース**: SQLite (Turso)
- **デプロイ**: Google Cloud Run
- **CI/CD**: GitHub Actions

## ディレクトリ構成（予定）
```text
.
├── app/
│   ├── main.py          # エントリポイント
│   ├── models.py        # SQLAlchemyモデル
│   ├── schemas.py       # Pydanticスキーマ
│   ├── auth.py          # 認証関連ロジック
│   ├── database.py      # DB接続設定
│   └── routers/         # APIルート分割
├── docs/                # 設計ドキュメント
├── tests/               # テストコード
├── Dockerfile           # コンテナ定義
├── requirements.txt     # 依存ライブラリ
└── .github/             # GitHub Actions設定
```
