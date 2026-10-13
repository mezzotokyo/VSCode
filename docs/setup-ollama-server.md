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

> 既定の Ollama は**ログイン中のユーザーセッション**で動作し、そのユーザーが
> ログアウトすると停止する。開発クライアントからいつでも接続できる常設サーバーに
> する（ログアウト・再起動後も稼働させる）場合は、各 OS の「常駐化」を実施する。
>
> - macOS: [§3.4 ログアウト後も稼働させる](#34-ログアウト後も稼働させる常駐化)
> - Windows: [§4.5 ログアウト後も稼働させる](#45-ログアウト後も稼働させる常駐化)

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

### 3.4 ログアウト後も稼働させる（常駐化）

3.1〜3.3 は**ログイン中のユーザーセッション**で Ollama を動かす構成であり、
ログアウトすると停止する。開発クライアントからいつでも接続できる常設サーバーに
するには、ユーザーのメニューバーアプリではなく、**システム領域の LaunchDaemon**
として登録する。

1. メニューバーの Ollama を **Quit** して停止する（同じ 11434 番ポートの競合を防ぐ）。
   `~/Library/LaunchAgents/com.ollama.ollama.plist` が存在する場合は無効化しておく
   （`launchctl bootout gui/$(id -u)/com.ollama.ollama`）。

2. `/Library/LaunchDaemons/com.ollama.server.plist` を次の内容で作成する。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.ollama.server</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Applications/Ollama.app/Contents/Resources/ollama</string>
    <string>serve</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>OLLAMA_HOST</key>
    <string>0.0.0.0:11434</string>
    <key>OLLAMA_MODELS</key>
    <string>/Users/Shared/ollama/models</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/var/log/ollama.out.log</string>
  <key>StandardErrorPath</key>
  <string>/var/log/ollama.err.log</string>
</dict>
</plist>
```

> `launchctl setenv`（3.2）で設定した環境変数は LaunchDaemon には引き継がれない。
> `OLLAMA_HOST` は plist の `EnvironmentVariables` に直接書く。デーモンは root として
> 動くためモデルの既定パスが変わる。`OLLAMA_MODELS` で格納先を明示し、既存モデルを
> そのパスへ移すか、改めて `ollama pull` する。

3. 所有者と権限を設定する（launchd は group/other が書き込み可能な plist を拒否する）。

```sh
sudo chown root:wheel /Library/LaunchDaemons/com.ollama.server.plist
sudo chmod 644 /Library/LaunchDaemons/com.ollama.server.plist
```

4. ロードして起動する。

```sh
sudo launchctl bootstrap system /Library/LaunchDaemons/com.ollama.server.plist
```

5. 状態を確認する。

```sh
sudo launchctl print system/com.ollama.server | head -n 20
curl http://<サーバーIP>:11434/api/version
```

**ログアウト／再起動後**に、クライアントから
`curl http://<サーバーIP>:11434/api/version` が返れば常駐化は成功。

停止・解除する場合:

```sh
sudo launchctl bootout system /Library/LaunchDaemons/com.ollama.server.plist
sudo rm /Library/LaunchDaemons/com.ollama.server.plist
```

Homebrew 版の Ollama を使う場合は、`sudo brew services start ollama` がシステム領域の
LaunchDaemon として登録する。ただし既定の環境変数に `OLLAMA_HOST` は含まれないため、
上記のように plist を直接作成する方が確実である。Homebrew 未導入の場合は、先に次で
導入する（初回のみ）。

```sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

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
対して許可** を選ぶ。逃した場合は、**管理者権限の PowerShell** で次を実行して許可する。

```powershell
New-NetFirewallRule -DisplayName "Ollama LAN" -Direction Inbound -LocalPort 11434 -Protocol TCP -Action Allow
```

### 4.4 疎通確認

```powershell
ipconfig
curl.exe http://<サーバーIP>:11434/api/version
```

> Windows 11 には `curl.exe` が標準搭載されているが、**Windows PowerShell 5.1 では
> `curl` が `Invoke-WebRequest` のエイリアス**として予約されている。`curl` のままだと
> 引数の解釈が異なり意図どおりに動かないことがあるため、上の例のように `curl.exe` と
> 明示するか、`Invoke-RestMethod http://<サーバーIP>:11434/api/version` を使う。
> 以降の `curl` の例（§4.5、§5）も同様に読み替える。

### 4.5 ログアウト後も稼働させる（常駐化）

4.1〜4.4 は**ログイン中のユーザーセッション**で Ollama を動かす構成であり、
ログオフすると停止する。開発クライアントからいつでも接続できる常設サーバーに
するには、ログオンに依存しない **Windows サービス**として登録する。

> 先にトレイ常駐の Ollama を **Quit** し、スタートアップからの自動起動を無効に
> しておく（同じ 11434 番ポートの競合を防ぐ）。

常駐化には、任意の実行ファイルを Windows サービスとして登録できる
**NSSM**（Non-Sucking Service Manager）を使う。NSSM はパッケージマネージャーの
**Scoop** で導入する。以下はサーバーマシン上での操作である。

1. Scoop 未導入の場合は、通常のユーザー権限の PowerShell で Scoop 本体を導入する
   （初回のみ）。

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
```

> `Set-ExecutionPolicy` は、スクリプト実行が制限された既定環境（`Restricted`）でも
> インストーラを動かすため。`-Scope CurrentUser` なので管理者権限は不要。Scoop は
> 既定で `~\scoop` に導入され、`~\scoop\shims` が PATH に追加される。`scoop install`
> 直後に「コマンドが見つからない」と出る場合は、新しい PowerShell を開くか、次で
> 現在のシェルへ PATH を反映する。

```powershell
$env:Path += ";$env:USERPROFILE\scoop\shims"
```

2. Scoop が使えるようになったら、管理者権限の PowerShell で NSSM を導入し、
   `ollama.exe serve` をサービスとして登録する。

```powershell
scoop install nssm
nssm install Ollama "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" serve
nssm set Ollama AppEnvironmentExtra OLLAMA_HOST=0.0.0.0:11434 OLLAMA_MODELS=C:\ProgramData\Ollama\models
nssm set Ollama Start SERVICE_AUTO_START
nssm start Ollama
```

> `nssm install` の実行ファイルは実際のインストール先に合わせる。トレイ UI の
> `ollama app.exe` ではなく `ollama.exe serve` を使う。サービスはローカルシステム
> アカウントで動くためモデルの既定パスが変わる。`OLLAMA_MODELS` を
> `AppEnvironmentExtra` で明示し、既存モデルをそのパスへ移すか、改めて
> `ollama pull` する。

状態と再起動後の確認:

```powershell
Get-Service Ollama
curl.exe http://<サーバーIP>:11434/api/version
```

停止・解除する場合:

```powershell
nssm stop Ollama
nssm remove Ollama confirm
```

**ログオフ／再起動後**（サインインしなくても）、クライアントから
`curl.exe http://<サーバーIP>:11434/api/version` が返れば常駐化は成功。

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

> クライアントが Windows の場合、`curl` は先の注意（§4.4）に従い `curl.exe` または
> `Invoke-RestMethod` に読み替える。

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