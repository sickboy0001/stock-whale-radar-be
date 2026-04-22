Google OAuth の `AUTH_GOOGLE_ID` と `AUTH_GOOGLE_SECRET` を入手する手順：

## Google Cloud Console で OAuth 認証情報を取得する

### 1. Google Cloud プロジェクトの作成
1. [Google Cloud Console](https://console.cloud.google.com/) にアクセス
2. 左上のプロジェクト選択ドロップダウンから「新しいプロジェクト」を選択
3. プロジェクト名を入力（例：`stock-whale-radar`）して「作成」

### 2. OAuth 同意画面の設定
1. 左側メニューから「API とサービス」>「同意画面」を選択
2. 「ユーザータイプ」を選択（外部または内部）
3. 「アプリの登録」ボタンをクリック
4. 以下の情報を入力：
   - アプリ名：`Stock Whale Radar`
   - ユーザーサポート E メール：自分の E メールアドレス
   - 開発者連絡先：自分の E メールアドレス
5. 「スコープ」はデフォルトのままで OK（`openid`, `email`, `profile` が含まれているか確認）
6. 「テストユーザー」に自分の Google アカウントを追加
7. 「保存して続行」

### 3. 認証情報の作成
1. 左側メニューから「API とサービス」>「認証情報」を選択
2. 「認証情報を作成」>「OAuth クライアント ID」を選択
3. 「アプリケーションの種類」を「ウェブアプリケーション」に選択
4. 以下の設定を入力：
   - 名前：`Stock Whale Radar Web Client`
   - **許可されたリダイレクト URI**:
     - 開発環境：`http://localhost:8000/auth/google/callback`
     - 本番環境：`https://your-domain.com/auth/google/callback`
5. 「作成」

### 4. クライアント ID とシークレットの取得
作成後、以下の情報が表示されます：
- **クライアント ID** → `.env` の `AUTH_GOOGLE_ID` に設定
- **クライアントシークレット** → `.env` の `AUTH_GOOGLE_SECRET` に設定

### 5. `.env` ファイルへの設定
```env
# Google OAuth
AUTH_GOOGLE_ID=your-client-id.apps.googleusercontent.com
AUTH_GOOGLE_SECRET=your-client-secret
```

### 注意点
- クライアントシークレットは一度しか表示されないため、必ずコピーしてください
- 紛失した場合は、削除して新しく作成し直す必要があります
- 本番環境では、Google Cloud Console の「許可されたリダイレクト URI」に本番環境の URL を追加する必要があります