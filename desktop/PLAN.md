# desktop アプリ開発計画書 — 弾道シミュレーション（Windows/macOS ネイティブ GUI）

本計画書は、`range_calculator` の弾道シミュレーションを **デスクトップのネイティブ GUI** から
操作・可視化する `desktop/` アプリの開発計画を定義する。実装に着手する前の合意事項として
本ファイルを残し、実装後は `desktop/README.md` に利用手順を分離する。

---

## 1. 目的と背景

- `range_calculator/`（物理コア）と `webapp/`（ブラウザ UI + stdlib API）は既に存在し、
  物理計算は 89 件のテストで検証されている。
- 本計画の対象は、ブラウザを起動せずに単体で動く **デスクトップ GUI** を追加すること。
  物理計算は既存コアを再利用し、再実装しない。
- 対象 OS は **Windows 11（主）と macOS（副）**。配布は **単一実行ファイル**（Windows は
  `.exe`、macOS は `.app`）とする。

---

## 2. 技術選定

GUI フレームワークは **Python + Tkinter（ttk）** を採用する。

| 案 | mac 互換 | 既存資産の再利用 | 追加ツールチェーン | 単一 exe 化 |
|----|---------|----------------|------------------|-------------|
| **Python + Tkinter（採用）** | 標準同梱 | 物理コアを直接 import | なし | PyInstaller |
| Tauri 2 | 可 | webapp の React を再利用 | Rust + Xcode | 内蔵バンドラ |
| .NET (WPF / WinUI 3) | 不可（Avalonia のみ可） | 物理コアを C# に移植 | dotnet SDK | 内蔵 |
| Python + PySide6 (Qt) | 可 | 物理コアを直接 import | pip 依存追加 | PyInstaller |

採用理由:

1. **stdlib only 方針との一致** — 本リポジトリの API・物理コアは標準ライブラリのみで動く。
   Tkinter は Windows/macOS の Python に同梱され、新規実行時依存を増やさない。
2. **物理コアの再利用** — `ballistics` / `physics_config` をそのまま import できる。
3. **クロスプラットフォーム** — 同一コードから Windows `.exe` / macOS `.app` を生成可能。
4. **グラフも自作** — webapp が自作 SVG で描くのと同様、`tkinter.Canvas` で描画し、
   追加のチャートライブラリを要しない。

トレードオフ: Tk の見た目は素朴である。モダンな外観が必須となった場合は Tauri への
移行を再検討する（本計画のスコープ外）。

---

## 3. スコープ

`webapp/README.md` の機能と同等とする。

- 入力: 初速（スライダー）、発射角（スライダー）、抗力係数 `Cd`（プリセット選択）、
  刻み幅 `dt`（数値入力）、adaptive（トグル）
- 出力: 理想射程 / 実射程 / 低減率 / 飛行時間 / 着弾速度 / 積分ステップ数 /
  最短刻み（または刻み幅）/ 着弾有無、時間上限到達時の警告
- 軌跡チャート: 抗力ありの軌跡、理想射程の破線、発射点・着弾点
- エラーは日本語で表示（物理コアの英語例外を変換）

スコープ外（将来検討）: プロファイル保存、CSV エクスポート、複数条件比較。

---

## 4. ディレクトリ構成

```text
desktop/
  PLAN.md                # 本ファイル（開発計画）
  app.py                 # エントリ: Tk ルート・ttk UI の組み立て
  gui_model.py           # GUI 非依存の純ロジック（プリセット・検証・simulate グルー）
  trajectory_chart.py    # Canvas 製の軌跡チャート Widget
  errors.py              # 英語例外→日本語（server.py:67 の localize_error と同型）
  build.py               # PyInstaller を起動するビルドスクリプト（追跡対象）
  README.md              # 起動・ビルド・mac 手順（実装後に作成）
  tests/
    test_gui_model.py    # 純ロジックの単体テスト（Tk 不要）
    test_agreement.py    # server.py / App.tsx との対応漏れ検出
```

`.gitignore` に `desktop/build/` と `desktop/dist/` を追記する。

---

## 5. 物理コアの再利用

`webapp/server/server.py` と同じ方式で、`range_calculator/` を `sys.path` に追加して
import する。

```python
REPO_ROOT = Path(__file__).resolve().parents[1]
RANGE_CALCULATOR = REPO_ROOT / "range_calculator"
if str(RANGE_CALCULATOR) not in sys.path:
    sys.path.insert(0, str(RANGE_CALCULATOR))

from ballistics import ProjectileSimulator, SimulationDiverged  # noqa: E402
from physics_config import DEFAULT_PARAMETERS  # noqa: E402
```

物理計算のロジックは再実装せず、既存の 89 件テストの庇護下に置く。軌跡は
`run_simulation(on_step=record)` の観測フックで収集する（`server.py:140` と同じ）。

---

## 6. UI 仕様（webapp との対応）

移植元は `webapp/src/App.tsx`。既定値・範囲・文言を一致させる。

| 項目 | 単位 | 既定値 | 範囲 / 選択肢 | 移植元 |
|------|------|--------|--------------|--------|
| 初速 | km/h | 170 | 10–500（スライダー） | `App.tsx:107` |
| 発射角 | deg | 35 | 1–89（スライダー） | `App.tsx:123` |
| 抗力係数 `Cd` | — | 0.47 | 4 プリセット（下記） | `App.tsx:8` |
| 刻み幅 `dt` | s | 0.01 | 0.0001–10、0.0001 単位 | `App.tsx:23` |
| adaptive | — | off | チェックボックス | `App.tsx:182` |

抗力係数プリセット（`webapp/src/App.tsx:8-13`）:

| 値 | ラベル |
|----|--------|
| 0.47 | 球体（既定値） |
| 0.348 | MLB（無回転） |
| 0.358 | MLB（2500rpm, 自由飛行） |
| 0.3 | NPB |

Result メトリクス（`App.tsx:213-248`）:

- 理想射程（抗力なし） m
- 実射程（抗力あり） m
- 到達距離の低減率 `(理想 - 実射程) / 理想 × 100` %
- 飛行時間 s
- 着弾速度 m/s
- 積分ステップ数
- 最短刻み（adaptive 時）/ 刻み幅（固定刻み時） s — 小数表示
- 着弾 yes / no

`timed_out` のときは「時間上限に達しました」警告を表示（`App.tsx:208-212`）。
dt のバリデーション文言（`App.tsx:42-56`）も移植する。

---

## 7. 軌跡チャート（Canvas）

移植元は `webapp/src/components/TrajectoryChart.tsx`。ロジックを `tkinter.Canvas` に移植する。

- `niceStep` による目盛りの「切りの良い」刻み幅計算（`TrajectoryChart.tsx:13`）
- 軸・グリッド線と目盛りラベル
- 軌跡ポリライン（青、`#2f80ed`、線幅 2.5 相当）
- 理想射程の縦破線（オレンジ、`#f2994a`、破線）
- 発射点（緑 `#27ae60`）と着弾点（赤 `#eb5757`）のマーカー
- 軸ラベル（横: horizontal distance x (m)、縦: height y (m)）
- スケーリング: `xDomain = maxX * 1.05`, `yDomain = maxY * 1.15`（`TrajectoryChart.tsx:43-44`）

---

## 8. 応答性（スレッド設計）

`dt = 0.0001` かつ `max_time = 300 s` では最大 300 万ステップとなり得るため、計算は
メインスレッドで行わない。

- ワーカースレッドで `simulate` を実行し、結果（または例外）を `queue.Queue` に渡す。
- `root.after()` によるポーリングで UI を更新し、計算中は「計算中...」を表示。
- 完了時に Result とチャートを更新、`timed_out` 警告・エラーを日本語で表示する。

---

## 9. 重複許容と対応漏れ防止

`server.py` との間に次の重複を **許容** する（各エントリポイントを自己完結させるため）。
ただし、片方だけ変更して他方が追随しない「対応漏れ」を、`tests/test_agreement.py` で
検出する。

| 重複対象 | 対応元 | 検出方法 |
|----------|--------|----------|
| 日本語エラー変換 | `webapp/server/server.py:67` `localize_error` | 代表的な英語メッセージ集合を両実装に通し、出力文字列の完全一致を assert |
| 抗力係数プリセット | `webapp/src/App.tsx:8` `DRAG_PRESETS` | `App.tsx` を正規表現でパースし、値・ラベルの一致を assert |
| simulate グルー | `webapp/server/server.py:121` `simulate` | 基準シナリオ (170, 35, dt=0.01) を両者で実行し、主要メトリクスの一致を assert |

`gui_model.py` / `errors.py` の先頭コメントには「対応元パス」と「`test_agreement.py` が
同期を保証している」旨を明記し、編集者が更新漏れに気付けるようにする。

なお `test_range_calc.py:184` にソースを読み取って検査する前例があるため、
`App.tsx` のパースによる同期検査は本リポジトリの慣例の範囲内である。

---

## 10. テスト方針

| 種別 | コマンド | 期待 |
|------|----------|------|
| desktop 純ロジック | `python3 -m unittest discover -s desktop/tests -p "test_*.py"` | 全パス |
| 物理コア（既存） | `python3 -m unittest discover -s range_calculator -p "test_*.py"` | `Ran 89 tests` / `OK` |
| 文字混入検査 | `python3 tools/check_text_hygiene.py` | `0 finding(s)` |

GUI そのものはヘッドレスで検証しにくいため、検証可能なロジック（プリセット・dt 検証・
低減率計算・エラー変換・simulate グルー・チャートのスケーリング計算）を `gui_model.py` と
`trajectory_chart.py` に分離し、Tk に依存させずに単体テストする。

---

## 11. 単一実行ファイル化（Windows / macOS）

`desktop/build.py` が PyInstaller を起動する。

- `--onefile --windowed`
- `--paths range_calculator`（非パッケージのコアモジュールを検出させる）
- `--add-data "range_calculator/config/physics_constants.json<pathsep>config"`
  - PyInstaller は非パッケージの `physics_config` をバンドル直下に展開するため、
    `Path(physics_config.__file__).parent / "config"` に一致するよう配置先を `config` とする。
  - `<pathsep>` は `os.pathsep`（Windows `;` / macOS `:`）で吸収する。
- 出力先は `desktop/dist/`（Windows `.exe` / macOS `.app`）。

実行時依存は標準ライブラリのみ。PyInstaller は **ビルド時のみ** のツールとし、venv で
`pip install pyinstaller` する手順を README に記載する。ビルド後の実行ファイルを起動し、
物理定数の config 警告が出ないことを確認する。

---

## 12. ドキュメント

- `desktop/README.md` を追加（起動 `python3 desktop/app.py`、ビルド手順、macOS 差異）。
- `docs/setup-windows.md` と `range_calculator/SPEC.md` 第11章に desktop の一行を追記
  （Python のみで動作し、追加の実行時依存が無い旨）。

---

## 13. 実装順序

1. `gui_model.py` / `errors.py`（純ロジック）と `tests/test_gui_model.py`
2. `trajectory_chart.py`
3. `app.py`（UI・スレッド）
4. `tests/test_agreement.py`（対応漏れ防止）
5. `build.py` + `desktop/README.md` + `docs` 追記 + `.gitignore`
6. 全テスト・文字混入検査・実機起動確認

---

## 14. 未確定事項

- ディレクトリ名は `desktop/` で確定（macOS 互換を踏まえた命名）。
- `server.py` とのロジック重複は許容し、対応漏れはテストで検出する方針で確定。
- PyInstaller の導入はビルド時のみ（venv で `pip install`）で確定。

---

*最終更新: 初版作成（2026-10-10）*
