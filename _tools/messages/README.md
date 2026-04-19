# messages/

送信テンプレート置き場。用途ごとに 1 ファイル（例: `shicho_mark.yml`）。

## 書式
`_template.yml` を参照。必須キー:
- `subject` 件名
- `body` 本文
- `敬称` 自治体名の後につける呼称
- `差出人.氏名` / `差出人.住所` / `差出人.電話` / `差出人.メール`

任意:
- `body_html` — HTML メール本文（email 経路のみ。フォーム送信では無視）

## 変数置換
`{{自治体名}}`, `{{敬称}}`, `{{差出人.氏名}}` などを本文・件名で使える。

## 呼び出し例
```
python _tools/send_all.py --message _tools/messages/shicho_mark.yml --dry-run --limit 5
```
