



EDINET APIの仕様（`?date=YYYY-MM-DD` のように1日単位でリクエストする仕様）を考慮すると、**「対象日（カレンダーの日付）ごとに、取得が完了しているかを管理する」**というアプローチが最適です。

これにより、バッチの抜け漏れ（休日やサーバーダウンで取得できなかった日）を検知し、期間指定で一括リカバリすることが可能になります。

この要件を満たすための**新しいテーブル設計**と、**管理画面（UI）のワイヤーフレーム案**をご提案します。


前提：
FastAPI側にも実装すること
管理者のみ利用可能とする
admin/import_daily_status/の下に配置するものとする。

---

### 1. テーブル設計：カレンダーベースのステータス管理

前回のジョブ管理をさらに実用的にし、**「対象日」を主キー（PK）としたテーブル**を作成します。

#### 📊 `import_daily_status`（日別インポート状況テーブル）
「2026年4月21日のEDINETデータは取り込み済みか？」を管理します。

```sql
CREATE TABLE import_daily_status (
  target_date       TEXT PRIMARY KEY,        -- 例: '2026-04-21'
  status            TEXT NOT NULL,           -- 'pending', 'processing', 'completed', 'failed'
  total_docs_count  INTEGER DEFAULT 0,
  target_docs_count INTEGER DEFAULT 0,
  success_count     INTEGER DEFAULT 0,
  last_run_start_at DATETIME,                -- 実行開始時間
  last_run_end_at   DATETIME,                -- 実行終了時間
  error_message     TEXT
);
```


**💡 このテーブルのメリット:**
画面上で「4月1日〜4月10日」を指定してインポートを実行した場合、バックエンドはカレンダーの日付を1日ずつループし、このテーブルの `status` を更新しながら処理を進めます。画面側はこのテーブルを `SELECT` するだけで、カレンダーUIを簡単に作れます。

---

### 2. 画面UI案：インポート管理ダッシュボード

管理者（開発者）が取り込み状況を一目で把握し、操作できる画面です。FastAPI,BootStrapで構築するイメージです。

#### 🖥️ UIレイアウト構成（ワイヤーフレーム）

```text
[ Stock Whale Radar - 管理者ダッシュボード ]

================================================================
▼ 手動インポート実行 (期間指定)
================================================================
admin/import_daily_status/import
 [ 開始日: 2026-04-01 📅 ]  〜  [ 終了日: 2026-04-21 📅 ]
 
 [ 🚀 指定期間のインポートを開始する ]  ←ボタン
 ※未実施(pending) または エラー(failed) の日付のみを対象に実行します。

================================================================
▼ 月間ステータスカレンダー (GitHubの草のようなヒートマップ)
================================================================
admin/import_daily_status/month

 [◀ 前月]   2026年 4月   [次月 ▶]

 [月] [火] [水] [木] [金] [土] [日]
            [01] [02] [03] [04] [05]
            🟩   🟩   🟩   ⬜️   ⬜️  
 [06] [07] [08] [09] [10] [11] [12]
  🟩   🟩   🟩   🟩   🟥   ⬜️   ⬜️
 [13] [14] [15] [16] [17] [18] [19]
  🟩   🟩   🟩   🟩   🟩   ⬜️   ⬜️
 [20] [21] [22]
  🟩   🟨   ⬜️

 凡例: 🟩 完了(completed)  🟥 エラー(failed)  🟨 処理中(processing)  ⬜️ 未実施(pending/データ無)

================================================================
▼ 直近の取り込み詳細リスト (import_daily_status)
================================================================
admin/import_daily_status/recent

 対象日      | ステータス | 大量保有(060) | 最終実行日時        | アクション
 ----------------------------------------------------------------------
 2026-04-21 | 🟨 処理中  | - / -         | 2026-04-21 12:00:00 | [強制停止]
 2026-04-20 | 🟩 完了    | 12件 / 12件   | 2026-04-20 20:05:12 | [再取得]
 2026-04-19 | ⬜️ 未実施  | 0件 / 0件     | -                   | [取得]
 2026-04-10 | 🟥 エラー  | 5件 / 8件     | 2026-04-10 16:30:00 | [詳細][再取得]
```

#### ✨ UIの主要機能とUXのポイント

1.  **直感的なカレンダー表示（ヒートマップ）**
    *   EDINETは土日祝日は基本的にデータがありません。そのため、カレンダー形式で「平日なのに赤（エラー）や白（未実施）になっている日」を視覚的に探せるようにするのが最も効率的です。
2.  **一括実行パネル**
    *   期間を指定してボタンを押すと、バックエンドのAPI（FastAPI）に非同期リクエストを投げます。
    *   バックエンド側では、すでに `completed` になっている日はスキップ（Skip）し、未取得の日だけを安全に取りに行くロジックにします。
3.  **アクションボタン（個別再取得）**
    *   リストビューの右側に `[再取得]` ボタンを置きます。特定の日にEDINET側で訂正書類が大量に出た場合など、その日だけをピンポイントで強制的に再取得（リトライ）できるようにします。

---

### 3. バックエンド（API）との連携イメージ

Next.jsの画面から、期間指定のインポートを実行した際の動きです。

**1. Next.js (フロント) ➔ FastAPI (バックエンド)**
*   POST `/api/admin/import`
*   Body: `{"start_date": "2026-04-01", "end_date": "2026-04-21"}`

**2. FastAPI (バックエンド) の処理**
```python
def run_period_import(start_date, end_date):
    # 1. 期間内の日付リストを生成 (例: ['2026-04-01', '2026-04-02', ...])
    date_list = generate_date_range(start_date, end_date)
    
    for target_date in date_list:
        # 2. Tursoで該当日のステータスを確認
        status_row = db.query("SELECT status FROM import_daily_status WHERE target_date = ?", target_date)
        
        # 3. 完了済みならスキップ
        if status_row and status_row.status == 'completed':
            continue
            
        # 4. ステータスを processing にして EDINET API を取得開始
        db.execute("INSERT OR REPLACE INTO import_daily_status (target_date, status) VALUES (?, 'processing')", target_date)
        
        try:
            # 実際のEDINET取得・XBRL解析処理を実行...
            fetch_and_parse_edinet(target_date)
            
            # 5. 成功したら completed に更新
            db.execute("UPDATE import_daily_status SET status = 'completed' WHERE target_date = ?", target_date)
        except Exception as e:
            # 6. 失敗したら failed に更新
            db.execute("UPDATE import_daily_status SET status = 'failed', error_message = ? WHERE target_date = ?", (str(e), target_date))
```

この「日別管理テーブル」と「管理ダッシュボード」があれば、過去5年分のデータを初期ロードする際も、日々の定期バッチがコケた時のリカバリも、画面のボタン一つで安全に運用できるようになります！



---

---

### 2. FastAPI バックエンド実装案

FastAPIの `APIRouter`、`Jinja2Templates`、そして時間のかかる取り込み処理を裏で回すための **`BackgroundTasks`** を使った実装例です。管理者用のBasic認証も組み込んでいます。

**`routers/admin_import.py`**
```python
from fastapi import APIRouter, Request, BackgroundTasks, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
from datetime import datetime, timedelta

router = APIRouter(prefix="/admin/import_daily_status", tags=["admin"])
templates = Jinja2Templates(directory="templates")
security = HTTPBasic()

# --- 簡易的な管理者認証 (本番では環境変数等から取得) ---
def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, "admin")
    correct_password = secrets.compare_digest(credentials.password, "secret_password")
    if not (correct_username and correct_password):
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})
    return credentials.username

# --- 裏で回す取り込み処理のダミー関数 ---
def background_import_task(start_date: str, end_date: str):
    print(f"[BACKGROUND TASK] {start_date} から {end_date} のインポートを開始...")
    # ここにDBを更新しながらEDINETから取得するロジックを書く
    # db.execute("UPDATE import_daily_status SET status = 'processing' WHERE ...")
    pass

# =========================================================
# 1. ダッシュボード画面表示 (カレンダーとリストを1画面にまとめるのがおすすめ)
# =========================================================
@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request, _=Depends(verify_admin)):
    # --- DBからデータを取得するダミー処理 ---
    # 実際は target_date DESC で直近10件などを取得
    recent_logs = [
        {"target_date": "2026-04-21", "status": "processing", "success": 0, "target": 0, "last_run": "2026-04-21 12:00:00"},
        {"target_date": "2026-04-20", "status": "completed", "success": 12, "target": 12, "last_run": "2026-04-20 20:05:12"},
        {"target_date": "2026-04-19", "status": "pending", "success": 0, "target": 0, "last_run": "-"},
        {"target_date": "2026-04-10", "status": "failed", "success": 5, "target": 8, "last_run": "2026-04-10 16:30:00"},
    ]
    
    # テンプレートにデータを渡してレンダリング
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "recent_logs": recent_logs,
        "current_month": "2026年 4月"
    })

# =========================================================
# 2. 期間指定のインポート実行 (POST)
# =========================================================
@router.post("/import")
async def execute_import(
    background_tasks: BackgroundTasks,
    start_date: str = Form(...),
    end_date: str = Form(...),
    _=Depends(verify_admin)
):
    # 取り込みは時間がかかるため、バックグラウンドで実行させる
    background_tasks.add_task(background_import_task, start_date, end_date)
    
    # リクエスト自体はすぐ返し、ダッシュボードへリダイレクト
    return RedirectResponse(url="/admin/import_daily_status/", status_code=303)

# =========================================================
# 3. 個別再取得 (POST)
# =========================================================
@router.post("/retry/{target_date}")
async def retry_import(
    target_date: str,
    background_tasks: BackgroundTasks,
    _=Depends(verify_admin)
):
    background_tasks.add_task(background_import_task, target_date, target_date)
    return RedirectResponse(url="/admin/import_daily_status/", status_code=303)
```

---

### 3. フロントエンド (Jinja2 + Bootstrap 5) 実装案

ご提示いただいたワイヤーフレームをそのままBootstrap5で構築したテンプレートです。
これを `templates/admin_dashboard.html` として保存します。

```html
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>Stock Whale Radar - 管理者ダッシュボード</title>
    <!-- Bootstrap 5 CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <!-- Bootstrap Icons -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css">
    <style>
        .cal-box { width: 30px; height: 30px; border-radius: 4px; display: inline-block; text-align: center; line-height: 30px; color: white; font-weight: bold;}
        .bg-completed { background-color: #198754; } /* 🟩 */
        .bg-failed { background-color: #dc3545; }    /* 🟥 */
        .bg-processing { background-color: #ffc107; color: black; } /* 🟨 */
        .bg-pending { background-color: #e9ecef; color: #6c757d; }  /* ⬜️ */
    </style>
</head>
<body class="bg-light">

<nav class="navbar navbar-dark bg-dark mb-4">
    <div class="container">
        <a class="navbar-brand" href="#"><i class="bi bi-radar"></i> Stock Whale Radar Admin</a>
    </div>
</nav>

<div class="container">
    
    <!-- ▼ 手動インポート実行 -->
    <div class="card mb-4 shadow-sm">
        <div class="card-header bg-white border-bottom-0">
            <h5 class="mb-0"><i class="bi bi-cloud-arrow-down"></i> 手動インポート実行 (期間指定)</h5>
        </div>
        <div class="card-body">
            <form action="/admin/import_daily_status/import" method="POST" class="row g-3 align-items-center">
                <div class="col-auto">
                    <label class="form-label">開始日</label>
                    <input type="date" class="form-control" name="start_date" required value="2026-04-01">
                </div>
                <div class="col-auto">
                    <label class="form-label">〜 終了日</label>
                    <input type="date" class="form-control" name="end_date" required value="2026-04-21">
                </div>
                <div class="col-auto mt-5">
                    <button type="submit" class="btn btn-primary"><i class="bi bi-rocket-takeoff"></i> 指定期間のインポートを開始する</button>
                </div>
            </form>
            <div class="form-text mt-2 text-muted">※未実施(pending) または エラー(failed) の日付のみを対象に実行します。</div>
        </div>
    </div>

    <!-- ▼ 月間ステータスカレンダー (簡易版) -->
    <div class="card mb-4 shadow-sm">
        <div class="card-header bg-white">
            <h5 class="mb-0"><i class="bi bi-calendar3"></i> 月間ステータス</h5>
        </div>
        <div class="card-body text-center">
            <h6 class="mb-3">
                <a href="#" class="btn btn-sm btn-outline-secondary">◀ 前月</a>
                <span class="mx-3 fw-bold">{{ current_month }}</span>
                <a href="#" class="btn btn-sm btn-outline-secondary">次月 ▶</a>
            </h6>
            <!-- ここはJinja2のループで動的に生成します（今回はモック） -->
            <div class="d-flex justify-content-center gap-1 mb-1">
                <div class="cal-box bg-completed" title="01日">1</div>
                <div class="cal-box bg-completed" title="02日">2</div>
                <div class="cal-box bg-pending" title="03日">3</div>
            </div>
            
            <div class="mt-3 small">
                凡例: 
                <span class="badge bg-success mx-1">完了</span>
                <span class="badge bg-danger mx-1">エラー</span>
                <span class="badge bg-warning text-dark mx-1">処理中</span>
                <span class="badge bg-secondary mx-1">未実施</span>
            </div>
        </div>
    </div>

    <!-- ▼ 直近の取り込み詳細リスト -->
    <div class="card shadow-sm mb-5">
        <div class="card-header bg-white">
            <h5 class="mb-0"><i class="bi bi-list-task"></i> 直近の取り込み詳細</h5>
        </div>
        <div class="table-responsive">
            <table class="table table-hover mb-0 align-middle">
                <thead class="table-light">
                    <tr>
                        <th>対象日</th>
                        <th>ステータス</th>
                        <th>大量保有 (保存/対象)</th>
                        <th>最終実行日時</th>
                        <th>アクション</th>
                    </tr>
                </thead>
                <tbody>
                    {% for row in recent_logs %}
                    <tr>
                        <td class="fw-bold">{{ row.target_date }}</td>
                        <td>
                            {% if row.status == 'completed' %}
                                <span class="badge bg-success">完了</span>
                            {% elif row.status == 'failed' %}
                                <span class="badge bg-danger">エラー</span>
                            {% elif row.status == 'processing' %}
                                <span class="badge bg-warning text-dark">処理中</span>
                            {% else %}
                                <span class="badge bg-secondary">未実施</span>
                            {% endif %}
                        </td>
                        <td>{{ row.success }}件 / {{ row.target }}件</td>
                        <td>{{ row.last_run }}</td>
                        <td>
                            <form action="/admin/import_daily_status/retry/{{ row.target_date }}" method="POST" class="d-inline">
                                {% if row.status == 'processing' %}
                                    <button type="button" class="btn btn-sm btn-outline-danger" disabled>強制停止</button>
                                {% else %}
                                    <button type="submit" class="btn btn-sm btn-outline-primary">再取得</button>
                                {% endif %}
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

</div>
</body>
</html>
```

### 💡 運用上のワンポイントアドバイス

1.  **「強制停止」の実装について**
    Pythonで動いているスレッド（BackgroundTasks）を外部から強制終了（キル）するのは、技術的にかなり難易度が高いです。
    もし強制停止を実装したい場合は、プロセスをキルするのではなく、DBのステータスを `failed` （または `canceled`）に書き換え、Pythonのバッチ処理のループ内で `if status == 'canceled': break` のように**フラグを見て自己終了させる実装（キャンセレーション）**にするのが安全な定石です。
2.  **カレンダーの描画**
    カレンダー部分は、FastAPIのバックエンド側で `calendar` モジュールを使って「今月の週と日の2次元配列」を作成し、それにDBのステータスをくっつけてJinja2に渡す（マッピングする）と、非常に綺麗にレンダリングできます。

この構成があれば、ローカル環境でも本番環境でも、ブラウザからポチッとボタンを押すだけでEDINETのデータを自在に取り込める、最高の運用環境が完成します！