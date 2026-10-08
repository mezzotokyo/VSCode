# Windows 11 セットアップ手順

native Windows 11（WSL を使わない構成）で本リポジトリを開発するための手順。
想定構成は **Python Install Manager**（Microsoft Store 版）と **Git for Windows**。
macOS と挙動を合わせるため、コマンド例は `python3` 表記で統一している。

## 1. 必要なソフト

| ソフト | 用途 | 備考 |
|--------|------|------|
| Python 3.9 以上 | 本体・テストの実行 | Python 3.14 で検証済み。Python Install Manager 槙成なら `python3` / `python` / `py` のどれでも起動できる |
| Git for Windows | リポジトリ操作・フック実行 | フックは POSIX シェルで書かれているが、Git for Windows は `sh` を同梱しているためそのまま動く |

Python が未導入の場合は Microsoft Store で「Python Software Foundation」提供の
パッケージをインストールする（有償の表示が出ている場合は選択を間違えている）。

## 2. Python の確認

PowerShell で次を実行する。

```powershell
python --version
python3 --version
py --version
```

すべて同じバージョン（例: `Python 3.14.8`）が返れば準備完了。

解決先のパスを知りたい場合は次のいずれかを使う。**`where python` は使わない**
（PowerShell の `where` は `Where-Object` のエイリアスであり、何も返さない）。

```powershell
(Get-Command python).Source
where.exe python
```

構成の目安:

- `python` / `python3` / `py` の3つがすべて動く → Python Install Manager（推奨構成）
- パスが `%LocalAppData%\Microsoft\WindowsApps` を指す → ストア経由の解決

## 3. リポジトリの取得と検証

```powershell
git clone <リポジトリのURL>
cd <リポジトリ名>
python3 -m unittest discover -s range_calculator -p "test_*.py"
python3 tools/check_text_hygiene.py
python3 range_calculator/range_calc.py
```

期待値:

- テスト: `Ran 89 tests` / `OK`
- 文字混入検査: `0 finding(s)`
- `range_calc.py`: シミュレーション結果が表示される

`python3` が無い環境では `python` に読み替える。

## 4. pre-commit フックの有効化

クローンごとに一度だけ、リポジトリルートで次を実行する。

```powershell
git config core.hooksPath .githooks
```

以降、コミットのたびに文字混入検査が自動実行され、混入文字が 1 件でもあれば
コミットが拒否される。フックを一時的に迂回したい場合のみ
`git commit --no-verify` を使う。

## 5. 注意事項

- **`data.csv` を Excel で開いて保存しない。** 保存すると BOM または
  Shift_JIS で書き戻され、読み込み時に既定値へ退避（またはエラー）の原因になる。
  編集はテキストエディタで行い、エンコーディングは UTF-8 のままとする。
- **改行コードは LF で固定されている**（リポジトリルートの `.gitattributes`）。
  `core.autocrlf` の設定に関わらず作業ツリーは LF のまま保たれる。
- **バージョン要件は Python 3.9 以上。** 現在は 3.14 で検証している。
- Store 版 Python は自動更新される。更新後にテストが落ちた場合は
  `python --version` でバージョン差分を確認する。

## 6. 関連文書

- 物理モデル・テスト仕様: `range_calculator/SPEC.md`（第11章に開発環境と検証手順）
- 変更履歴: `range_calculator/HISTORY.md`
