# ローカルLLM環境構築と弾道シミュレーション

本地にローカル LLM 推論サーバー（Ollama）を構築して opencode から利用する手順と、
弾道シミュレーション（range_calc）の物理計算コアと 3 つの利用形態
（CLI / Web / デスクトップ GUI）からなるプロジェクトです。

等質・球形の弾丸を水平面に対して真上方向へ初速 `v0` で発射したとき、2 次式
ドラッグ（空力抵抗）を考慮して**地面衝突までの距離と飛行時間**を数値積分で求めます。

> 本ツールは**到達距離の相対比較と傾向分析**のためのものであり、実測弾道
> データとの絶対一致や競技規則的精度を要求する用途には用いません
> （適用限界は `range_calculator/SPEC.md` 第7章に詳細）。

---

## 1. リポジトリ構成

```text
.
├── range_calculator/    # 物理計算コア（Python 標準ライブラリのみ）
│   ├── range_calc.py        # CLI（シナリオ実行）
│   ├── ballistics.py        # ODE ソルバ（RK4 / 適応刻み）
│   ├── physics_config.py    # 物理定数の読み込み・検証
│   ├── config/              # physics_constants.json（物理定数）
│   ├── test_*.py            # テスト（54 + 35 件）
│   ├── SPEC.md              # 物理モデル仕様書
│   ├── HISTORY.md           # 変更履歴
│   └── archive/             # 旧バージョン（V0〜V4）
├── webapp/              # Web アプリ（Vite + React + TypeScript + stdlib API）
├── desktop/             # デスクトップ GUI（Tkinter、実行時依存なし）
├── docs/                # 環境構築・推論サーバー構築手順
├── tools/               # 開発支援ツール（文字混入検査・bootstrap）
├── .githooks/           # pre-commit フック
└── opencode.json        # opencode（開発支援 CLI）の設定
```

| ディレクトリ | 説明 | 主なドキュメント |
|--------------|------|------------------|
| `range_calculator/` | 物理コア。全形態がこれを再利用する | `SPEC.md` |
| `webapp/` | ブラウザで操作・可視化する Web アプリ | `webapp/README.md` |
| `desktop/` | ブラウザ不要のネイティブ GUI アプリ | `desktop/README.md` |
| `docs/` | 環境構築・セットアップ手順 | 下記 [`§6 ドキュメント`](#6-ドキュメント) |
| `tools/` | 文字混入検査・pre-commit フック設定 | — |
| `opencode.json` | AI 開発支援 CLI（opencode）のプロバイダ設定 | `docs/setup-ollama-server.md` |

---

## 2. 環境構築

### 2.1 前提

| ソフト | 用途 | 備考 |
|--------|------|------|
| Python 3.9 以上 | 物理コア・テスト・文字混入検査 | 標準ライブラリのみ。3.15 で検証 |
| Node.js 20.19+ / 22.12+ | `webapp` の開発サーバ・ビルド | Vite 8 の要件。`webapp` 以外は不要 |
| Ollama | ローカル LLM 推論サーバー | opencode から OpenAI 互換 API で接続 |

環境構築の詳細は以下を参照してください。

- **macOS / Linux / 共通**: `docs/setup-machine.md`
- **Windows 11（Scoop）**: `docs/setup-windows.md`
- **Ollama 推論サーバー（macOS / Windows）**: `docs/setup-ollama-server.md`

### 2.2 LLM 推論サーバーの構築（Ollama）

開発用エージェントには **opencode**、LLM プロバイダーには**オープンソースの
Ollama** を使用します。LLM プロバイダーは **LAN 内のサーバー上に構築**する想定です。

> **サーバーとクライアントを同居させない。**
> 推論サーバーと開発クライアントを同一マシン上に載せると、モデルのメモリ使用量と
> ビルド・エディタ・エージェントの負荷が重なり、マシンメモリの逼迫により動作が
> 重くなります。そのため、サーバーは開発マシンとは別に LAN 上へ構築します。

サーバー環境を構築しない場合でも、opencode が提供する**無料モデル**や、
契約済みのプロバイダーを利用することも可能です。

Ollama は既定で `127.0.0.1:11434` にしかバインドしないため、**LAN 公開には
`OLLAMA_HOST=0.0.0.0:11434` の設定が必須**です。

- macOS: `launchctl setenv OLLAMA_HOST "0.0.0.0:11434"`（Ollama アプリ再起動）
- Windows: ユーザー環境変数に `OLLAMA_HOST=0.0.0.0:11434` を追加（Ollama 再起動）

モデルの取得:

```sh
ollama pull gemma4:e4b      # opencode.json の gemma4:e4b-mlx 系のベースモデル
ollama pull qwen3.5:4b      # qwen3.5:4b-mlx-64k のベースモデル
ollama list
```

詳細な手順（Modelfile でのエイリアス作成・ファイアウォール設定・疎通確認）は
`docs/setup-ollama-server.md` を参照してください。

### 2.3 pre-commit フックの有効化

クローンごとに一度だけ:

```sh
bash tools/bootstrap.sh .
```

または、`git config core.hooksPath .githooks` のみでも有効です（クローン済みの場合）。
以降、コミット時に文字混入検査が自動実行されます。

### 2.4 AI 開発支援（opencode）

`opencode.json` で Ollama の推論サーバーを参照しています。プロバイダ定義と
モデル一覧は同ファイル、サーバー構築手順は `docs/setup-ollama-server.md` を
参照してください。

Ollama サーバーを構築しない場合は、opencode が提供する**無料モデル**を利用
するか、**契約済みのプロバイダー**（API キー等）を `opencode.json` に定義して
切り替えることができます。

### 2.5 新規リポジトリの作成（雛形配布）

複数プロジェクトを扱う場合、**プロジェクト単位でリポジトリを分離**します。
本リポジトリは雛形（テンプレート）として、`tools/bootstrap.sh` で各新リポジトリへ
pre-commit フック・文字混入検査・`.gitattributes`・`.gitignore` 一式を配布できます。

```sh
# 1. ホストで空リポジトリを作成（GitHub の場合）
gh repo create <名前> --private

# 2. クローン
git clone <new-origin> 新しいプロジェクト && cd 新しいプロジェクト

# 3. 雛形を配布（既存リポジトリのパスを指定）
bash /path/to/本リポジトリ/tools/bootstrap.sh .

# 4. 初期ファイルをコミットして push
git add . && git commit -m "init" && git push -u origin main
```

opencode のプロバイダ定義（Ollama）はグローバル設定
（`~/.config/opencode/opencode.json`）に置かれているため、新リポジトリ側に
`opencode.json` を用意する必要はありません。

---

## 3. 物理モデル概要

`range_calculator/SPEC.md` の要点です。

### 3.1 基礎方程式

質量で割った加速度形式の 4 元状態 `(x, y, vx, vy)` を陽的 4 次ルンゲ–クッタ（RK4）で
積分します。

```text
dx/dt  = vx
dy/dt  = vy
dvx/dt = -k · vx · |v|
dvy/dt = -k · vy · |v| - g

|v| = sqrt(vx² + vy²)
```

| 記号 | 意味 | 既定値 |
|------|------|--------|
| `g` | 重力加速度 | 9.81 m/s² |
| `ρ` | 空気密度 | 1.225 kg/m³ |
| `Cd` | 抗力係数 | 0.47（球体代表値。MLB / NPB プリセットあり） |
| `m` | 弾丸質量 | 0.149 kg |
| `d` | 弾丸直径 | 0.075 m |
| `k` | 抗力係数 `= 0.5·ρ·A·Cd / m` | 8.535522e-03 m⁻¹ |

### 3.2 数値解法

- **固定刻みモード**: `dt`（既定 0.01 s）固定。局所誤差 `O(dt⁵)`
- **適応刻みモード（`adaptive=True`）**: 安定性上限 `dt_max = 0.5 / (k·|v|)` を
  超えないよう必要時にのみ刻みを短縮（発散防止機構。精度向上は保証しない）
- 地面衝突（`y = 0`）はステップ内を**線形補間**して確定
- 発散検出・時間上限（既定 300 s）・初心者向けの数値ガードあり

### 3.3 基準シナリオ（`170 km/h`, `35°`, `dt=0.01`）

| 指標 | 値 |
|------|-----|
| 理想射程（抗力なし） | 213.60 m |
| 実射程（抗力あり） | 101.12 m |
| 飛行時間 | 4.37 s |
| 抗力による低減率 | 約 52.7 % |

---

## 4. 利用形態

### 4.1 CLI（`range_calculator/range_calc.py`）

```sh
python3 range_calculator/range_calc.py [scenario_path] [dt_max] [--adaptive] [--v0=<km/h>] [--angle=<deg>]
```

```sh
python3 range_calculator/range_calc.py                      # 既定シナリオ（data.csv）
python3 range_calculator/range_calc.py data.csv 0.01 --adaptive --v0=170 --angle=35
```

### 4.2 Web アプリ（`webapp/`）

Vite + React + TypeScript のフロントと、Python 標準ライブラリのみの JSON API
（`stdlib`）で構成。物理計算はコアを再利用します。

```sh
# ターミナル A: API サーバ
python3 webapp/server/server.py --port 8000

# ターミナル B: フロント（別ターミナル）
cd webapp && npm run dev
# → http://127.0.0.1:5173/
```

詳細: `webapp/README.md`

### 4.3 デスクトップ GUI（`desktop/`）

Python 標準ライブラリの Tkinter（ttk）によるネイティブ GUI。追加の `pip`
パッケージなしで動作し、PyInstaller で単一実行ファイルをビルドできます。

```sh
python3 desktop/app.py
```

詳細: `desktop/README.md`

---

## 5. 検証・品質

- **物理コアのテスト**: 89 件（`test_range_calc.py` 54 件 + `test_adaptive_timestep.py` 35 件）
  - 解析解（`k=0`）との一致 / 収束性 / 着弾状態 / 回帰 / パラメータ検証 /
    シミュレータ契約 / 数値ガード
- **desktop のテスト**: 25 件（GUI 純ロジック 18 件 + webapp との対応漏れ検査 7 件）
- **文字混入検査**: `python3 tools/check_text_hygiene.py`
  （`0 finding(s)` が正常。pre-commit フックに組み込み）

```sh
python3 -m unittest discover -s range_calculator -p "test_*.py"
python3 -m unittest discover -s desktop/tests -p "test_*.py"
python3 tools/check_text_hygiene.py
```

> **注意**: テストはフラット import（`import ballistics` 等）を使うため、カレント
> ディレクトリに注意してください（リポジトリルートから実行します）。

---

## 6. ドキュメント

| ドキュメント | 内容 |
|--------------|------|
| `range_calculator/SPEC.md` | 物理モデル仕様・テスト仕様・適用限界 |
| `range_calculator/HISTORY.md` | 変更履歴（V0〜V4 の変遷） |
| `webapp/README.md` | Web アプリの起動・API・構成 |
| `desktop/README.md` | デスクトップ GUI の起動・ビルド・テスト |
| `desktop/PLAN.md` | デスクトップアプリの開発計画書 |
| `docs/setup-machine.md` | 環境構築（macOS / Linux / 共通） |
| `docs/setup-windows.md` | 環境構築（Windows 11 / Scoop） |
| `docs/setup-ollama-server.md` | Ollama 推論サーバー構築（opencode 接続用） |

---

## 7. ライセンス

記載なし（プライベートリポジトリ）。詳細はリポジトリ管理者に確認してください。
