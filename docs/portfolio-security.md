# ポートフォリオ公開前のセキュリティ確認

確認日: 2026-10-04。対象はVercel/Neon Terraform、Next.jsのBFF・Server Guard、FastAPIの公開境界・DB接続。リポジトリ全体の侵入テストを完了したという意味ではない。

## 適用済みのクラウド設定

- Vercel `syncnesto-portfolio` をHobbyで作成。Productionの `BFF_SHARED_SECRET` はSensitive変数として登録。DBの資格情報は渡していない。GitHubは未接続で、Previewの自動デプロイは無効。
- Vercel `syncnesto-portfolio-api` をFastAPI用に作成。共有キー・JWT署名キーと安全な本番設定を登録。まだruntimeのDB・S3接続情報は登録せず、アプリはデプロイしていない。
- Neon `syncnesto-portfolio` (`misty-band-66896279`) をFreeで作成。PostgreSQL 17、Singapore、0.25 CU固定。Freeの停止時間は明示変更できないため既定に従う。
- `syncnesto_owner` はmigration専用。アプリはSQLで作成した `syncnesto_app` を使う。Neon APIで作るロールの管理権限をアプリへ与えない。
- アプリはCONNECT、public schemaのUSAGE、テーブルのSELECT/INSERT/UPDATE/DELETE、シーケンスのUSAGE/SELECTのみ。PUBLICのDB権限を剥奪し、管理ロールが将来作るテーブルにもdefault privilegesを設定。接続数20、statement timeout 30秒。ロールの管理権限・継承・replication・RLS bypassは無効。
- 管理資格情報はVercelやブラウザへ渡さない。state・planはGit管理外。実行ヘルパーは新規秘密ファイルを所有者専用の権限で作る。stateには秘密が含まれるためバックアップも公開しない。

## 実装した防御

| 確認した課題 | 対策 | 確認方法 |
| --- | --- | --- |
| 当初のruntime URIが管理ユーザーだった | 制限付きロールと管理接続を分離 | Neonへの実通信でCRUD成功、DDL・管理操作はSQLSTATE 42501 |
| バックエンドの直接公開でBFFを迂回できる | 共有キーを定数時間で比較し、健康確認以外は必須 | 不正キー403、正しいキーでもCSRFが必要なテスト |
| 公開APIでの大量ログイン・DBリクエスト | 業務処理前にIP単位でログイン10回/分・その他240回/分、全体6000回/分。PostgreSQLでinstance間共有 | 429・Retry-After・並行20要求で10件だけ許可・期限切れ削除・DB障害503のテスト |
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

バックエンド: ruff・pyright成功、pytest 445 passed / 5 skipped / 3 xfailed。フロント: format・typecheck・lint・build成功。Terraform: project・database・runtime構成のvalidate・mockテスト成功。runtimeは秘密設定待ちで未適用。skip/xfailは既存テストの条件による。

## 公開前に残る作業と制限

- FastAPIのVercelプロジェクトは作成済み。Supabase `syncnesto` プロジェクトを確認したが、組織のFreeプラン確認とS3キーの発行は未完了。制限付きDATABASE_URLとS3資格情報をruntime構成から登録する。
- 管理URIでアプリの全migration（共有カウンターを含む）を適用済み。初期seedは未実行で、ローカルのデータを移していない。管理資格情報はruntimeに渡さない。
- Supabaseにprivate bucket・署名付きアップロード・未完了オブジェクトの清掃を用意する。S3 bucket CORS/lifecycle APIは非対応のため、実際のプラットフォームCORS応答と別の清掃運用を検証する。
- Backend URLをVercelへ登録し、変更を反映したコードでデプロイした後に、実URLでログイン・Cookie属性・権限・CSRF・429・直接API拒否を再確認する。現在は公開されたWebアプリの実URLを検証していない。
- Neon FreeではIP Allowが使えず、DBへの接続試行そのものは遮断できない。TLS・認証・権限で守る。資格情報が漏えいした場合は読み書きの被害を防げないため、ロールのパスワードを更新する。
- IP制限はPostgreSQLで共有し、HMAC化したIPを保存する。同一プロセス内の事前制限も併用する。DDoS・分散攻撃・無料枠の消費を完全に防ぐものではない。Vercelには標準のDDoS保護があるが、カスタムWAFルールは作成していない。

## 公式資料

- [Neon IP Allow](https://neon.com/docs/introduction/ip-allow)
- [Neonロールと権限](https://neon.com/docs/manage/roles)
- [Neon Scale to Zero](https://neon.com/docs/introduction/scale-to-zero)
- [Vercelのリクエストヘッダー](https://vercel.com/docs/headers/request-headers)
- [Vercel DDoS保護](https://vercel.com/docs/security/ddos-mitigation)
