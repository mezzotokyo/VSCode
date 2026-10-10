# Range Calculator Desktop (desktop)

`range_calculator` の弾道シミュレーションを、ブラウザを使わずにネイティブ GUI で
操作・可視化するデスクトップアプリです。GUI は Python 標準ライブラリの Tkinter
（ttk）で構築し、物理計算は既存の `range_calculator`（`ballistics` /
`physics_config`）をそのまま再利用します。

対応 OS は **Windows 11（主）** と **macOS（副）** です。実行時依存は Python 標準
ライブラリのみで、追加の `pip` パッケージは不要です（ビルド時のみ PyInstaller を
使います。§4）。

機能は `webapp` と同等です（入力・Result メトリクス・軌跡チャート）。対応関係と
設計の詳細は `desktop/PLAN.md` を参照してください。

---

## 1. 前提環境

- **Python 3.9 以上**（Windows: `python` / `python3`、macOS: `python3`）
- Tkinter（Python 同梱。Scoop の Python 3.14 / python.org 版で動作確認）
  - Tk のバージョン確認: `python3 -c "import tkinter; print(tkinter.TkVersion)"`

追加の `pip` パッケージは不要です。

---

## 2. 起動方法

リポジトリのルートで実行します。

Windows:

```powershell
python desktop/app.py
```

macOS:

```sh
python3 desktop/app.py
```

起動時に既定値（初速 170 km/h、発射角 35 deg、Cd 0.47、dt 0.01）で 1 回自動実行
されます。

---

## 3. 操作方法

1. **初速** と **発射角** のスライダーを動かす。
2. **抗力係数 Cd** をプルダウンで選ぶ（球体 0.47 / MLB 0.348 / MLB 0.358 / NPB 0.3）。
3. 必要に応じて **刻み幅 dt**（0.0001–10、0.0001 単位）を変更し、**adaptive** を
   有効にする。
4. 「**シミュレーション実行**」を押す。計算中は `計算中...` を表示し、完了すると
   **Result** にメトリクス、下段 **Trajectory** に軌跡チャートが表示される。
5. エラー時は Result を更新せず、日本語のエラーメッセージを表示する。

`adaptive` は刻みを安定性上限内に短縮する発散防止機構であり、精度向上を保証する
ものではありません（詳細は `range_calculator/SPEC.md` 第4章）。

---

## 4. 単一実行ファイルのビルド（任意）

配布用の自己完結ファイルを作る場合は PyInstaller を使います。**ビルド時のみ**
必要で、アプリの実行には不要です。

```sh
pip install pyinstaller
python3 desktop/build.py
```

- Windows: `desktop/dist/range_calculator_desktop.exe`
- macOS: `desktop/dist/range_calculator_desktop`（必要なら `.app` 化）

`build.py` は物理定数の設定ファイル（`range_calculator/config/physics_constants.json`）を
実行ファイルに同梱します。ビルド後、実行ファイルを起動して物理定数の
`physics config not found` 警告が出ないことを確認してください。

---

## 5. テスト

リポジトリのルートで実行します。

```sh
python3 -m unittest discover -s desktop/tests -p "test_*.py"
python3 -m unittest discover -s range_calculator -p "test_*.py"
python3 tools/check_text_hygiene.py
```

`desktop/tests/test_agreement.py` は、`webapp` と意図的に重複させている
エラー変換・Cd プリセット・simulate グルーが食い違っていないかを検査します。
`webapp` 側を変更したら、`desktop` 側も追随させてください（詳細は
`desktop/PLAN.md` §9）。

---

## 6. 構成

```text
desktop/
  app.py                 # エントリ: Tk ルート・ttk UI の組み立て
  gui_model.py           # GUI 非依存の純ロジック（プリセット・検証・simulate）
  trajectory_chart.py    # Canvas 製の軌跡チャート
  errors.py              # 英語例外→日本語
  build.py               # PyInstaller によるビルド
  PLAN.md                # 開発計画書
  tests/
    test_gui_model.py    # 純ロジックの単体テスト
    test_agreement.py    # webapp との対応漏れ検出
```

---

## 7. トラブルシューティング

| 症状 | 原因 / 対処 |
|------|-------------|
| `ModuleNotFoundError: tkinter` | Python に Tk が含まれていない。python.org 版または Scoop の Python を使う |
| 起動しても何も表示されない | 追加の `pip` 依存は不要。`python3 desktop/app.py` をフォアグラウンドで実行しエラーを確認する |
| `physics config not found` 警告 | 設定ファイルが見つからず組み込み既定値で動作。ビルド版では `build.py` の同梱設定を確認する |
| 計算が長い | `dt` を大きくするか `adaptive` を有効にする。`dt=0.0001`・時間上限 300 s では最大 300 万ステップになり得る |

---

## 8. 関連ドキュメント

- 開発計画書: `desktop/PLAN.md`
- 物理モデル・テスト仕様: `range_calculator/SPEC.md`
- Web アプリ（同等機能のブラウザ版）: `webapp/README.md`
- 環境構築（Windows 11）: `docs/setup-windows.md`
- 環境構築（macOS / 共通）: `docs/setup-machine.md`
