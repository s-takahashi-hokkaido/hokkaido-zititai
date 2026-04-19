# credentials/

Gmail API 用の OAuth クライアント情報とトークンを置くディレクトリ。
**`.gitignore` で中身は git 追跡しない**（README のみ追跡）。

## 初回セットアップ（Gmail OAuth）

### 1. Google Cloud Console で OAuth クライアントを作成
1. https://console.cloud.google.com/ にログイン（`s.takahashi.hokkaido@gmail.com`）
2. 新規プロジェクト作成（例: `hokkaido-zititai-mailer`）
3. 「APIとサービス」→「ライブラリ」→ **Gmail API を有効化**
4. 「APIとサービス」→「OAuth 同意画面」
   - User Type: **外部**（個人 Gmail アカウントでは「内部」は選べない）
   - アプリ名: 任意
   - テストユーザー: `s.takahashi.hokkaido@gmail.com` を追加
   - スコープ欄は**触らなくてよい**（新 UI では登録画面自体スキップされる。実スコープ `gmail.send` は初回 OAuth 時にクライアントライブラリが要求し同意画面に自動表示される）
5. 「APIとサービス」→「認証情報」→「認証情報を作成」→ **OAuth クライアントID**
   - アプリケーションの種類: **デスクトップアプリ**
   - 名前: `send_all`
6. 作成後、**JSONをダウンロード** → このディレクトリに `gmail_oauth.json` として保存

### 2. 初回送信時のブラウザ同意
最初に `python _tools/send_all.py` を本送信モードで実行すると、ブラウザが開き同意画面が出る。
同意すると `gmail_token.json` がここに保存され、以降は自動更新される。

### 3. ファイル
- `gmail_oauth.json` — Google から落とした OAuth クライアント情報（手動で配置）
- `gmail_token.json` — 同意後に自動生成される token（削除すると再同意が必要）
- どちらも `.gitignore` で除外済み。絶対に push しないこと。

## トラブルシュート

- **`access_denied` エラー**: OAuth 同意画面の「テストユーザー」に `s.takahashi.hokkaido@gmail.com` が登録されているか確認
- **`invalid_client`**: `gmail_oauth.json` のダウンロード元プロジェクトと同じ Google アカウントで同意しているか確認
- **token 期限切れ**: `gmail_token.json` を削除して再実行すれば再同意できる
