# ポートフォリオ公開前のセキュリティ確認

確認日: 2026-10-04。対象はVercel/Neon Terraform、Next.jsのBFF・Server Guard、FastAPIの公開境界・DB接続。リポジトリ全体の侵入テストを完了したという意味ではない。

## 適用済みのクラウド設定

- Vercel `syncnesto-portfolio` をHobbyで作成。Productionの `BFF_SHARED_SECRET` はSensitive変数として登録。DBの資格情報は渡していない。GitHubは未接続で、Previewの自動デプロイは無効。
- Neon `syncnesto-portfolio` (`misty-band-66896279`) をFreeで作成。PostgreSQL 17、Singapore、0.25 CU固定。Freeの停止時間は明示変更できないため既定に従う。
- `syncnesto_owner` はmigration専用。アプリはSQLで作成した `syncnesto_app` を使う。Neon APIで作るロールの管理権限をアプリへ与えない。
- アプリはCONNECT、public schemaのUSAGE、テーブルのSELECT/INSERT/UPDATE/DELETE、シーケンスのUSAGE/SELECTのみ。PUBLICのDB権限を剥奪し、管理ロールが将来作るテーブルにもdefault privilegesを設定。接続数20、statement timeout 30秒。ロールの管理権限・継承・replication・RLS bypassは無効。
- 管理資格情報はVercelやブラウザへ渡さない。state・planはGit管理外。実行ヘルパーは新規秘密ファイルを所有者専用の権限で作る。stateには秘密が含まれるためバックアップも公開しない。

## 実装した防御

| 確認した課題 | 対策 | 確認方法 |
| --- | --- | --- |
| 当初のruntime URIが管理ユーザーだった | 制限付きロールと管理接続を分離 | Neonへの実通信でCRUD成功、DDL・管理操作はSQLSTATE 42501 |
| バックエンドの直接公開でBFFを迂回できる | 共有キーを定数時間で比較し、健康確認以外は必須 | 不正キー403、正しいキーでもCSRFが必要なテスト |
| 公開APIでの大量ログイン・DBリクエスト | DB処理前にIP単位でログイン10回/分・その他240回/分 | 429・Retry-After・時間枠回復・有限カウンターのテスト |
| ブラウザによる内部キー/IP偽装 | BFFで内部ヘッダーを上書きし、Vercel管理のIPだけ採用 | BFFヘッダー偽装・秘密未設定・応答漏えい防止テスト |
| 本番設定漏れ | Secure Cookie・Cookie-only認証・強い署名キー・明示Host・DB証明書検証・SQLログ無効を起動条件にする | 危険な設定の起動拒否テスト |
| 公開APIドキュメント・開発用CORS | productionのSwagger/ReDoc/OpenAPIと開発CORSを無効化 | 本番設定のルート404・Host制限のテスト |
| ブラウザの埋め込み・MIME判定など | DENY、nosniff、Referrer/Permissions Policy、frame-ancestors/base-uri/object-src制限 | ローカルの本番HTTP応答で確認 |

既存のHttpOnly Cookie、CSRF、アカウント単位のログイン失敗ロック、セッション、permission/RBACチェックは維持している。CSPは埋め込み等の基本制限であり、全スクリプトをnonceで制限する完全なXSS対策ではない。

## 実通信で確認したDB保護

`scripts/verify_portfolio_database.py` で新規UUID付きテーブルを作り、以下を確認して削除した。DB資格情報を標準出力へ表示しない。

- directとruntime poolerの両接続で、OSのCAによる証明書・ホスト名検証とTLS通信が成功。
- アプリロールに管理権限・`neon_superuser` membershipがない。
- 将来作られるテーブルのINSERT/SELECT/UPDATE/DELETEとserial sequenceは成功。
- CREATE TABLE、CREATE ROLE、CREATE DATABASE、管理ロール所有テーブルのDROPは権限不足で拒否。
- 不正パスワード、SSL無効、CAファイル不足の接続は、それぞれ該当する理由で拒否。
- 検証用テーブル・シーケンス等を削除。Terraformの両stateは適用後のplanで差分なし。

バックエンド: ruff・pyright成功、pytest 440 passed / 5 skipped / 3 xfailed。フロント: format・typecheck・lint・build成功。Terraform:両構成のvalidate・mockテスト成功。skip/xfailは既存テストの条件による。

## 公開前に残る作業と制限

- FastAPIホストと公開用オブジェクトストレージはまだ作成していない。実ホストへ制限付きDATABASE_URL、BFF_SHARED_SECRET、強いSECRET_KEY、APP_ENV=production、ALLOWED_HOSTS、Secure Cookie設定を登録する。
- 管理URIでmigration・初期seedを行い、runtimeに管理資格情報を残さない。公開デモ専用データを使い、ローカル開発データを無断で移さない。
- オブジェクトストレージにはprivate bucket、公開OriginだけのCORS、署名付きアップロード、未完了オブジェクトの清掃設定を用意する。
- Backend URLをVercelへ登録し、変更を反映したコードでデプロイした後に、実URLでログイン・Cookie属性・権限・CSRF・429・直接API拒否を再確認する。現在は公開されたWebアプリの実URLを検証していない。
- Neon FreeではIP Allowが使えず、DBへの接続試行そのものは遮断できない。TLS・認証・権限で守る。資格情報が漏えいした場合は読み書きの被害を防げないため、ロールのパスワードを更新する。
- IP制限は単一プロセス内。再起動でリセットされ、複数worker/instanceで共有しない。DDoS・分散攻撃・無料枠の消費を完全に防ぐものではない。Vercelには標準のDDoS保護があるが、カスタムWAFルールは作成していない。

## 公式資料

- [Neon IP Allow](https://neon.com/docs/introduction/ip-allow)
- [Neonロールと権限](https://neon.com/docs/manage/roles)
- [Neon Scale to Zero](https://neon.com/docs/introduction/scale-to-zero)
- [Vercelのリクエストヘッダー](https://vercel.com/docs/headers/request-headers)
- [Vercel DDoS保護](https://vercel.com/docs/security/ddos-mitigation)
