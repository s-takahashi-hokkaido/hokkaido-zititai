# \_tools/ — 自治体一括連絡ツール群

北海道179自治体に対して、メール or フォーム経由で一括メッセージを送信するためのツール一式。

## 全体像（ハイブリッド方式）

1. Claude に「〇〇を全自治体に送って」と指示
2. Claude が本ツールを bash で kick
3. ツールが夜間にバッチ送信（email / Playwright form）
4. 翌朝ログ（`logs/send_log.jsonl`）を Claude に読ませて結果サマリ

## ファイル構成

```
_tools/
├── send_all.py          # CLI エントリ：全体オーケストレーション
├── md_parser.py         # `北海道/**/*.md` を Municipality dataclass で読む
├── log_store.py         # JSONL 形式のログ読み書き（クラッシュ耐性）
├── discover_fields.py   # Playwright で form URL を調査しフィールド一覧を出力
├── senders/
│   ├── mail.py          # Gmail API 経由の送信
│   └── form.py          # Playwright 経由のフォーム送信
├── messages/
│   ├── README.md
│   └── _template.yml    # 本文テンプレート（subject / body / 差出人）
├── logs/                # 送信ログ・スクショ（中身は .gitignore 除外）
├── credentials/         # Gmail OAuth クライアント情報（中身は .gitignore 除外）
└── discover/            # discover_fields の出力（.md は追跡、.png は除外）
```

## 実行方法

```bash
# dry-run（内容だけログ、実送信しない）
python _tools/send_all.py --message _tools/messages/_template.yml --dry-run

# 地方で絞り込み、最初の5件だけ
python _tools/send_all.py --message ... --include-region 石狩地方 --limit 5

# メール送信のみ、中札内村だけ
python _tools/send_all.py --message ... --include-method email --only 中札内村

# 途中で Ctrl+C したあと再開
python _tools/send_all.py --message ... --resume

# form URL の入力欄を Playwright で一括調査
python _tools/discover_fields.py --resume
```

## 現在の到達状況（2026-04-19 時点）

| 連絡手段 | 自治体数 | 状態 |
| --- | --- | --- |
| email | 48 | 送信可能（Gmail API 動作確認済み） |
| form（フィールド確定済み） | 107 + 5 | 送信可能 |
| form（`&check` 2段階CMS） | 5 | 網走・美幌・鷹栖・厚沢部を確定、送信側未対応 |
| form（要個別対応） | 6 | 江別（ラベル誤爆）、興部（LoGo申請ボタン）、ニセコ・倶知安・小樽（案内ページ）、鷹栖以外の残り |
| form（CAPTCHA） | 15 | `skipped: captcha` として対象外 |
| tel | 8 | デジタル連絡不可として対象外（幌加内町含む） |

合計 179 件のうち **送信可能 160 件** / 要対応 11 件 / 対象外 15 件+8 件。

## 既知の制約と対処

### detail.php?sec_sec1=X&check 系 CMS（ホームページビルダー系）

- `&check` 付きURLはサーバーが Cookie 検証するため、`&check` 無し版を先に踏んでからでないとフォーム本体が表示されない
- `discover_fields.py` は対処済み（トップページ訪問 → `&check` 除去版訪問 → 本URL訪問）
- **`form.py` は未対応**（実送信時には同様の2段階踏みが必要）

該当: 網走市・美幌町・鷹栖町・厚沢部町 の4件

### LoGoフォーム landing page

- logoform.jp 系の一部が「このまますぐに申請する」ボタン経由でしか入れない
- 該当: 興部町（他3件は直接入れた）

### 案内ページ問題

- 登録URLが問合せフォームへの**リンク集ページ**で、代表窓口のフォーム直URLがMD側にない
- 鷹栖町は `sec_sec1=2&inq=04&check`（総務係）を手動特定
- 厚沢部町は `sec_sec1=2&check`（総務財政課）を手動特定
- 残: ニセコ町・倶知安町・小樽市（代表窓口のフォーム直URL未特定）

### CAPTCHA

- reCAPTCHA 8件 + 画像CAPTCHA 7件 = 15件
- Playwright では原理的に突破不可（ボット判定のため）
- 2captcha 等の外部サービス必要、今回は**放置で確定**

## discover_fields.py 出力の読み方

`_tools/discover/{自治体名}.md` と `.png`（スクショ）のペアで出力される。

- `.png` を先に見る → 想定したフォームが映ってれば成功
- `.md` の「推奨フィールドテーブル」を `北海道/{振興局}/{自治体名}.md` の `### フォームフィールド` に反映
- `?` のフィールドは生データ部の `ancestorHeading` / `rowContext` / `aria-label` を頼りに手で埋める

## 開発履歴

- 2026-04-18: `send_all.py` 一式実装（md_parser / log_store / senders / messages）
- 2026-04-19:
  - Playwright 必須17件の調査用に `discover_fields.py` を追加
  - detail.php 系5件の Cookie 2段階仕様を発見、discover 側で対処
  - 帯広市・網走市・美幌町・鷹栖町・厚沢部町のフォームフィールドを反映
  - 幌加内町はフォーム不在のため `method=tel` に訂正
