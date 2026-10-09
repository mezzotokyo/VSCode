# Range Calculator Web (webapp)

`range_calculator` の弾道シミュレーションをブラウザで操作・可視化する Web アプリです。
フロントエンドは Vite + React + TypeScript、バックエンドは Python 標準ライブラリのみの
JSON API で構成され、物理計算は既存の `range_calculator`（`ballistics` / `physics_config`）を
そのまま再利用します。

---

## 1. 機能

### 1.1 入力（Launch conditions）

| 項目 | 単位 | 既定値 | 説明 |
|------|------|--------|------|
| 初速 | km/h | 170 | スライダー（10–20000） |
| 発射角 | deg | 35 | スライダー（1–89） |
| 刻み幅 `dt` | s | 0.01 | 数値入力（0.0001–5） |
| adaptive | — | off | 安定性上限で刻みを自動短縮するモード |

「シミュレーション実行」ボタンで API を呼び出し、結果が更新されます。

### 1.2 出力メトリクス（Result）

- 理想射程（抗力なし）: 閉形式 `v0^2 sin(2θ) / g`
- 実射程（抗力あり）: RK4 による着弾距離
- 到達距離の低減率: `(理想 - 実射程) / 理想 × 100` %
- 飛行時間
- 着弾速度
- 積分ステップ数
- 最短刻み（`adaptive` で短縮された場合のみ表示）
- 着弾したかどうか

時間上限（既定 300 s）に達した場合は警告を表示します。

### 1.3 軌跡チャート

独立した計算を行わず、シミュレーション中の各ステップを取得して SVG で描画します。

- 青い実線: 抗力ありの軌跡（横軸 x、縦軸 y）
- オレンジの破線: 理想射程（抗力なし）の位置
- 緑の点: 発射点 / 赤の点: 着弾点
- 依存するチャートライブラリは無し（自作 SVG）

### 1.4 API

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/api/health` | 死活確認（`{"status":"ok"}`） |
| GET | `/api/config` | 既定値と物理定数の既定プロファイル |
| POST | `/api/simulate` | 1回の発射を実行し、メトリクスと軌跡を返す |

`POST /api/simulate` のリクエスト例:

```json
{
  "velocity_kmph": 170,
  "angle_deg": 35,
  "dt": 0.01,
  "adaptive": false
}
```

任意で `parameters` オブジェクト（`max_time`, `gravity`, `air_density`, `mass`,
`diameter`, `drag_coefficient`）を指定すると物理定数を上書きできます。
軌跡は最大 2000 点に間引き（間引き）して返します。

---

## 2. 構成

```text
webapp/
  index.html
  package.json
  vite.config.ts        # dev サーバ設定（IPv4 固定・/api プロキシ）
  src/
    main.tsx
    App.tsx             # 画面本体
    api.ts              # fetch ラッパー
    types.ts            # API 型定義
    components/
      TrajectoryChart.tsx
  server/
    server.py           # stdlib のみの JSON API
```

開発時はフロント（5173）から API（8000）へ、Vite の dev プロキシ経由でアクセスします
（同一オリジンになるため CORS 設定は不要）。

---

## 3. 前提環境

いずれの OS でも必要なもの:

- **Python 3.9 以上**（Windows: `python` / `python3`、macOS: `python3`）
  - 追加の `pip` パッケージは不要。API と物理コアは標準ライブラリのみで動作します
- **Node.js 20.19 以上 / 22.12 以上**（Vite 8 の要件）と npm
  - `npm install` で React・Vite・TypeScript 等の依存は自動導入されます

### 3.1 Windows（Scoop）

未導入なら次で導入します。

```powershell
scoop install python nodejs git
```

Scoop 導入直後の古いシェルでは PATH が未反映の場合があります。新しい PowerShell を
開くか、次を実行してください。

```powershell
$env:Path += ";$env:USERPROFILE\scoop\shims;$env:USERPROFILE\scoop\apps\nodejs\current"
```

### 3.2 macOS

- Python: `xcode-select --install`（`/usr/bin/python3` が入る）、または `brew install python`
- Node.js: `brew install node`、または [nvm](https://github.com/nvm-sh/nvm) で導入

```sh
brew install node
```

macOS では Python を `python3`、Node を `npm` で起動します。Scoop の PATH 追記は不要です。

### 3.3 フロントの依存（全 OS 共通）

初回のみ、フロントの依存をインストールします。

```sh
cd webapp
npm install
```

---

## 4. 起動方法

API とフロントを**別々のターミナル**で起動します。

### 4.1 ターミナル A: API サーバ

リポジトリのルートで実行します（起動したままにする）。

Windows:

```powershell
python webapp/server/server.py --port 8000
```

macOS:

```sh
python3 webapp/server/server.py --port 8000
```

`RangeCalc API listening on http://127.0.0.1:8000` と表示されれば起動成功です。
ポートを変えたい場合は `--port` を変更し、`vite.config.ts` の `proxy.target` も合わせて
ください。

### 4.2 ターミナル B: フロントエンド

コマンドは Windows / macOS 共通です。

```sh
cd webapp
npm run dev
```

バナーが次のように表示されれば起動成功です（`127.0.0.1` 固定）。

```text
  ➜  Local:   http://127.0.0.1:5173/
```

ブラウザで **http://127.0.0.1:5173/** を開きます。
`localhost` ではなく `127.0.0.1` を使うのが確実です。

### 4.3 停止

各ターミナルで `Ctrl+C` を押します。プロセスが残ってしまった場合は次で掃除します。

Windows:

```powershell
Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
```

macOS:

```sh
pkill -f "vite" || true
pkill -f "server/server.py" || true
```

---

## 5. 操作方法

1. スライダーで **初速** と **発射角** を調整する。
2. 必要に応じて **刻み幅 dt** を変更、または **adaptive** を有効にする。
3. 「**シミュレーション実行**」を押す（計算中は `計算中...` 表示）。
4. **Result** にメトリクス、下段 **Trajectory** に軌跡チャートが表示される。
5. 条件を変えて再実行すると結果が更新される。初回表示時にも既定値で1回実行されます。

`adaptive` は刻みを安定性上限内に**短縮**する発散防止機構であり、精度向上を保証する
ものではありません（詳細は `range_calculator/SPEC.md` 第4章）。

---

## 6. 開発コマンド

`webapp` ディレクトリで実行します。

| コマンド | 内容 |
|----------|------|
| `npm run dev` | 開発サーバ起動（http://127.0.0.1:5173/） |
| `npm run build` | 型チェック（`tsc -b`）＋本番ビルド（`dist/` 生成） |
| `npm run preview` | ビルド成果物のプレビュー（API 連携には別途サーバが必要） |
| `npm run lint` | oxlint による静的解析 |

### 6.1 テスト

バックエンドが使う物理コアは既存のテストで検証されています（Windows は `python`、
macOS は `python3`）。

```sh
python3 -m unittest discover -s range_calculator -p "test_*.py"
python3 tools/check_text_hygiene.py
```

---

## 7. トラブルシューティング

| 症状 | 原因 / 対処 |
|------|-------------|
| ブラウザで `ERR_CONNECTION_REFUSED`（ページ自体） | dev サーバが IPv6 (`::1`) のみで待ち受けている。`vite.config.ts` は `host: '127.0.0.1'` 済み。`npm run dev` を**再起動**し、バナーが `127.0.0.1` になっているか確認 |
| `http proxy error: /api/... ECONNREFUSED 127.0.0.1:8000` | API サーバが未起動。ターミナル A で API を起動（Windows: `python webapp/server/server.py --port 8000` / macOS: `python3 ...`） |
| `Port 5173 is in use` | 古い Vite が残存。Windows: `Get-Process node \| Stop-Process -Force` / macOS: `pkill -f vite` |
| `node` / `npm` が見つからない | Scoop 導入後にシェルを開き直す。または §3.1 の PATH 追記を実行（macOS は `brew install node`） |
| `python: command not found`（macOS） | macOS では `python3` を使う |
| 画面に `エラー: ...` が出る | 入力値不正、または API 側の検証に失敗。メッセージ内容を確認 |

---

## 8. 関連ドキュメント

- 物理モデル・テスト仕様: `range_calculator/SPEC.md`
- 環境構築（macOS / 共通）: `docs/setup-machine.md`
- 環境構築（Windows 11）: `docs/setup-windows.md`
