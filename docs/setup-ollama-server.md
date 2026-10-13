# Ollama 推論サーバー構築手順（macOS / Windows）

LAN 内の 1 台を Ollama 推論サーバーとして構築し、別マシン上の **opencode** から
OpenAI 互換 API（`<サーバーIP>:11434/v1`）で接続するための手順。

- 接続元は **LAN 内の別マシン**（サーバー自身で開かない構成）
- プロバイダーは **Ollama** に限定する（LM Studio は使わない）
- 接続例: `http://192.168.20.34:11434/v1`

## 1. 全体構成

```text
┌──────────────────┐        HTTP/OpenAI互換API        ┌──────────────────────┐
│  クライアント     │ ───────────────────────────────▶│  推論サーバー          │
│  opencode        │    http://<サーバーIP>:11434/v1  │  Ollama :11434         │
└──────────────────┘                                   └──────────────────────┘
```

Ollama は既定で `127.0.0.1:11434` にしかバインドしないため、**LAN からの接続には
`OLLAMA_HOST` の変更が必須**である。OS 別の設定方法は次章以降。

## 2. 共通: モデルの準備

ベースモデルは **Ollama のモデルライブラリ**（`https://ollama.com/library`）から
取得する。ブラウザの検索欄（`https://ollama.com/search`）でモデル名を検索し、
ページに記載された `ollama run <モデル>` / `ollama pull <モデル>` のコマンドを
サーバー上で実行する。

```sh
ollama pull <モデル名>
ollama list
```

本リポジトリの `opencode.json` で定義しているモデルと、そのベースモデルの取得元:

| opencode.json のモデル ID | 名前 | ベースモデル（取得コマンド） |
|---------------------------|------|------------------------------|
| `gemma4:e4b-mlx` | Gemma 4 E4B (Ollama) | `gemma4:e4b`（`ollama pull gemma4:e4b`） |
| `gemma4:e4b-mlx-64k` | Gemma 4 E4B (64K) | `gemma4:e4b`（`ollama pull gemma4:e4b`） |
| `qwen3.5:4b-mlx-64k` | Qwen3.5 4B (64K) | `qwen3.5:4b`（`ollama pull qwen3.5:4b`） |

対応する MLX 系タグ（例: `gemma4:e4b-mlx-bf16`）がライブラリに存在する場合は
そのタグを直接 pull してもよい。64K 系は context を 65536 に制限したエイリアス
であり、クライアント側の `limit.context` で縛っている。`gemma4:e4b-mlx-64k`
などのタグが存在しない場合は、ベースモデルを pull したうえでローカルの Modelfile
でエイリアスを作り、`ollama create` する（例: `num_ctx` を 65536 に設定）。

## 3. macOS での構築

### 3.1 インストール

1. <https://ollama.com/download> からインストーラを取得し、`Ollama.app` を
   Applications へ配置する（または `curl -fsSL https://ollama.com/install.sh | sh`）。
2. 一度起動してバックグラウンド起動を確認する。

```sh
ollama --version
```

メニューバーアプリは **シェルの rc ファイル（`~/.zshrc` 等）を読まない**。
環境変数は `launchctl` で OS レベルに設定する。

### 3.2 LAN からの接続を許可

```sh
launchctl setenv OLLAMA_HOST "0.0.0.0:11434"
```

反映のため Ollama アプリを再起動する（メニューバーの Ollama → **Quit** → 再起動）。
ブラウザからの CORS を許可したい場合のみ:

```sh
launchctl setenv OLLAMA_ORIGINS "*"
```

### 3.3 サーバー IP の確認と疎通確認

```sh
ipconfig getifaddr en0
curl http://<サーバーIP>:11434/api/version
```

`curl` が `{"version":"..."}` を返せばサーバー側は準備完了。

> **注意**: `0.0.0.0` へのバインドは全ネットワークインターフェースに公開することに
> なる。信頼できる LAN でのみ行い、不要なら macOS のファイアウォール
> （システム設定 → ネットワーク → ファイアウォール）で 11434 を制限する。

## 4. Windows での構築

### 4.1 インストール

1. <https://ollama.com/download> からインストーラ（`.exe`）を取得して実行する。
2. タスクバーの Ollama アイコンでバックグラウンド起動を確認する。

### 4.2 環境変数の設定

Ollama は Windows のユーザー環境変数をそのまま継承する。

1. Ollama を終了する（タスクトレイのアイコン右クリック → **Quit**）。
2. **設定（Windows 11）またはコントロールパネル** → 環境変数の編集を開く。
3. ユーザー環境変数に新規作成:
   | 名前 | 値 |
   |------|----|
   | `OLLAMA_HOST` | `0.0.0.0:11434` |
4. 「適用」で保存し、Ollama を Start メニューから再起動する。

PowerShell（セッション内のみ）で一時確認する場合は次でもよい:

```powershell
$env:OLLAMA_HOST = "0.0.0.0:11434"
ollama serve
```

### 4.3 ファイアウォールの許可

初回起動時の Windows ファイアウォールのダイアログで **プライベートネットワークに
対して許可** を選ぶ。逃した場合は以下で許可する。

```powershell
New-NetFirewallRule -DisplayName "Ollama LAN" -Direction Inbound -LocalPort 11434 -Protocol TCP -Action Allow
```

### 4.4 疎通確認

```powershell
ipconfig
curl http://<サーバーIP>:11434/api/version
```

## 5. クライアント側（opencode）の設定

サーバーとは別のマシンのリポジトリで、`opencode.json` に provider を定義する。

```json
{
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama (local)",
      "options": {
        "baseURL": "http://<サーバーIP>:11434/v1"
      },
      "models": {
        "gemma4:e4b-mlx": {
          "name": "Gemma 4 E4B (Ollama)"
        },
        "gemma4:e4b-mlx-64k": {
          "name": "Gemma 4 E4B (64K)",
          "limit": {
            "context": 65536,
            "output": 8192
          }
        },
        "qwen3.5:4b-mlx-64k": {
          "name": "Qwen3.5 4B (64K)",
          "limit": {
            "context": 65536,
            "output": 8192
          }
        }
      }
    }
  }
}
```

- `<サーバーIP>` はサーバーの IP に置き換える。
- OpenAI 互換 API は `@ai-sdk/openai-compatible` で接続する。
- モデル ID はサーバーで `ollama list` したときの名前（タグ）と一致させる。

疎通確認（クライアントから）:

```sh
curl http://<サーバーIP>:11434/v1/models
```

モデル一覧が JSON で返れば接続成功。

## 6. 切り替え・モデル評価

プロバイダを切り替える場合は `opencode.json` の `"model"` を書き換えるか、
opencode 起動時のプロバイダ選択で Ollama 側を選ぶ。

opencode.json を編集したら opencode を**リロード**して反映する。

## 7. 参考

- Ollama FAQ（環境変数・ログなど）: <https://docs.ollama.com/faq>
- モデル格納先（既定）:
  - macOS: `~/.ollama/models`
  - Windows: `%USERPROFILE%\.ollama\models`
- ログ:
  - macOS: `~/.ollama/logs/server.log`
  - Windows: `%LOCALAPPDATA%\Ollama\server.log`
- opencode 設定の詳細: `opencode.json`（リポジトリルート）