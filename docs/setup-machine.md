# 環境再構築・新規リポジトリ手順（複数マシン共通）

複数のマシン（macOS / Windows / Linux）で同じツール群を利用し、新規に開発環境を
導入する場合や、新規プロジェクトでも同一の開発環境を再現するための共通手順。

前提: **各リポジトリが git リモート（origin）で管理されている**こと。
iCloud Drive 等のクラウド同期フォルダへの依存はしない（Linux でも同じ手順になる）。

## 1. 必要なソフト

| ソフト | 用途 | 備考 |
|--------|------|------|
| Python 3.9 以上 | 文字混入検査・テストの実行 | macOS: Xcode CLT ／ Windows: Python Install Manager ／ Linux: ディストリのパッケージ |
| Git | リポジトリ操作・フック実行 | フックは POSIX シェル。Windows は Git Bash の `sh` / `bash` で実行 |

各 OS の導入手順:

- **macOS**: `xcode-select --install` で `/usr/bin/python3` と `git` が入る。
  （Homebrew 利用の場合: `brew install python git`）
- **Windows**: Microsoft Store の「Python Software Foundation」製 Python と Git for Windows。
  詳細は `docs/setup-windows.md` を参照。
- **Linux (例: Ubuntu)**: `sudo apt install python3 git`

## 2. リポジトリの取得とフック有効化

新規に開発環境を導入するマシンでも共通。各リポジトリについて:

```sh
git clone <origin のURL> <ディレクトリ名>
cd <ディレクトリ名>
bash tools/bootstrap.sh .      # POSIX/Windows 共通。実行ビット無しでも動く
```

`tools/bootstrap.sh` は次のことを自動で行う（冪等・何度実行しても安全）:

1. 未初期化なら `git init`
2. `.githooks/pre-commit`・`tools/check_text_hygiene.py`・`.gitattributes` を配置（上書き）
3. `.gitignore` は雛形の行を差し込み（既存の行は保持）
4. `git config core.hooksPath .githooks`
5. `chmod +x .githooks/pre-commit`
6. 文字混入検査を実行して正常動作を確認

このスクリプトは自分自身が入っているリポジトリを雛形元にするため、
別プロジェクトにも配布できる（例: `bash /path/to/repo/tools/bootstrap.sh 新しいプロジェクト`）。

## 3. 検証

```sh
bash tools/check_text_hygiene.py      # 期待値: scanned N file(s), 0 finding(s)
bash tools/bootstrap.sh .            # 再実行しても失敗しない（冪等チェック）
```

任意でフック発火確認: ハングルを 1 文字混入させたファイルを一時的に追加して
`git commit` が拒否されることを確認し、元に戻す。

## 4. 新規リポジトリの作成

1. ホスト（GitHub / GitLab / Gitea 等）で空リポジトリを作成
2. `git clone <new-origin> myproj && cd myproj`
3. 雛形を配布: `bash <既存ツールのあるリポジトリ>/tools/bootstrap.sh .`
4. 初期ファイルをコミットして `git push -u origin <ブランチ名>`

複数のリポジトリを管理する場合は、各リポジトリで 2–4 を繰り返す。

## 5. 既存リポジトリに origin を張る

他人からもらったリポジトリなど、origin 未設定の場合は:

```sh
git remote add origin <origin のURL>
git push -u origin <ブランチ名>      # 例: main / v5
```

## 6. クロス機共通の注意

- **リポジトリの内部で `git clone` を実行しない。**
  ネストされたリポジトリが誤検出の原因になり、コミットがブロックされる。
- **`core.fileMode` は設定しない（各 OS の既定値のまま）。**
  macOS/Linux は `true`・Windows は `false` が正しい。共有コンフィグに書くと
  Windows で `.githooks/pre-commit` が常に `M` 表示になり、誤コミットで
  macOS/Linux のフックが黙って無効化される。
- **モードのみの変更（実行ビット）はコミットしない。**
  フックの `100755` はリポジトリで維持する。`M` が出るときは
  `chmod +x .githooks/pre-commit` で解消する（コミットは不要）。
- フックもリポジトリの一部として origin を介して配布されるため、
  各機での設定は clone 後の `bootstrap.sh` 実行のみで完結する。

## 7. 関連文書

- Windows 固有のセットアップ: `docs/setup-windows.md`
- 文字混入検査の仕様・ルール: `tools/check_text_hygiene.py` の docstring と `--list-rules`