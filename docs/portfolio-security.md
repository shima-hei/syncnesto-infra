# ポートフォリオ公開環境のセキュリティ確認

確認日: 2026-10-04。対象はVercel/Neon Terraform、Next.jsのBFF・Server Guard、FastAPIの公開境界・DB接続。リポジトリ全体の侵入テストを完了したという意味ではない。

## 適用済みのクラウド設定

- Vercel `syncnesto-portfolio` をHobbyで作成。Productionの `BFF_SHARED_SECRET` はSensitive変数として登録。DBの資格情報は渡していない。GitHubは未接続で、Previewの自動デプロイは無効。
- Vercel `syncnesto-portfolio-api` をFastAPI用に作成。共有キー・JWT署名キー、安全な本番設定、制限付きDB接続とS3キーを登録してデプロイ済み。DB・S3の資格情報はバックエンドだけに登録。
- フロントエンドは https://syncnesto.vercel.app 、バックエンドは https://syncnesto-portfolio-api.vercel.app で公開。フロントの公開ドメインはTerraformで管理し、本番デプロイへ自動割り当てする。BFF接続には追加の安定エイリアス `syncnesto-portfolio-api-shima-hei.vercel.app` を使用し、明示Hostに登録。
- Supabase Storageは利用者のBilling画面でFree・Spend cap有効を確認。非公開バケット、20MiBのファイル上限、600秒の署名URLを設定。Security advisorsの指摘は0件。
- Neon `syncnesto-portfolio` (`misty-band-66896279`) をFreeで作成。PostgreSQL 17、Singapore、0.25 CU固定。Freeの停止時間は明示変更できないため既定に従う。
- `syncnesto_owner` はmigration専用。アプリはSQLで作成した `syncnesto_app` を使う。Neon APIで作るロールの管理権限をアプリへ与えない。
- アプリはCONNECT、public schemaのUSAGE、テーブルのSELECT/INSERT/UPDATE/DELETE、シーケンスのUSAGE/SELECTのみ。PUBLICのDB権限を剥奪し、管理ロールが将来作るテーブルにもdefault privilegesを設定。接続数20、statement timeout 30秒。ロールの管理権限・継承・replication・RLS bypassは無効。
- 管理資格情報はVercelやブラウザへ渡さない。state・planはGit管理外。実行ヘルパーは新規秘密ファイルを所有者専用の権限で作る。stateには秘密が含まれるためバックアップも公開しない。
- Terraform stateは専用Neon DBへ移行し、アプリロールからの接続を拒否。PostgreSQL backendのadvisory lockを使用。GitHubの本番Environmentはmain限定、PRの検証へ本番Secretsを渡さない。詳細は [Actions運用](github-actions.md)。

## 実装した防御

| 確認した課題 | 対策 | 確認方法 |
| --- | --- | --- |
| 当初のruntime URIが管理ユーザーだった | 制限付きロールと管理接続を分離 | Neonへの実通信でCRUD成功、DDL・管理操作はSQLSTATE 42501 |
| バックエンドの直接公開でBFFを迂回できる | 共有キーを定数時間で比較し、健康確認以外は必須 | 不正キー403、正しいキーでもCSRFが必要なテスト |
| 公開APIでの大量ログイン・DBリクエスト | 業務処理前にIP単位でログイン10回/分・その他240回/分、全体6000回/分。PostgreSQLでinstance間共有 | 429・Retry-After・並行20要求で10件だけ許可・期限切れ削除・DB障害503のテスト |
| ブラウザによる内部キー/IP偽装 | BFFで内部ヘッダーを上書きし、Vercel管理のIPだけ採用 | BFFヘッダー偽装・秘密未設定・応答漏えい防止テスト |
| 本番設定漏れ | Secure Cookie・Cookie-only認証・強い署名キー・明示Host・DB証明書検証・SQLログ無効を起動条件にする | 危険な設定の起動拒否テスト |
| 公開APIドキュメント・開発用CORS | productionのSwagger/ReDoc/OpenAPIと開発CORSを無効化 | 本番設定のルート404・Host制限のテスト |
| ブラウザの埋め込み・MIME判定など | DENY、nosniff、Referrer/Permissions Policy、frame-ancestors/base-uri/object-src制限 | 本番HTTP応答で確認 |

既存のHttpOnly Cookie、CSRF、アカウント単位のログイン失敗ロック、セッション、permission/RBACチェックは維持している。CSPは埋め込み等の基本制限であり、全スクリプトをnonceで制限する完全なXSS対策ではない。

## 実通信で確認したDB保護

`scripts/verify_portfolio_database.py` で新規UUID付きテーブルを作り、以下を確認して削除した。DB資格情報を標準出力へ表示しない。

- directとruntime poolerの両接続で、OSのCAによる証明書・ホスト名検証とTLS通信が成功。
- アプリロールに管理権限・`neon_superuser` membershipがない。
- 将来作られるテーブルのINSERT/SELECT/UPDATE/DELETEとserial sequenceは成功。
- CREATE TABLE、CREATE ROLE、CREATE DATABASE、管理ロール所有テーブルのDROPは権限不足で拒否。
- 不正パスワード、SSL無効、CAファイル不足の接続は、それぞれ該当する理由で拒否。
- 検証用テーブル・シーケンス等を削除。Terraformの両stateは適用後のplanで差分なし。

バックエンド: ruff・pyright成功、pytest 445 passed / 5 skipped / 3 xfailed。フロント: format・typecheck・lint・build成功、Nodeテスト27件成功。Terraform: project・database・runtime構成のvalidate・mockテスト成功、全構成適用済み。skip/xfailは既存テストの条件による。

## 公開URLでの実通信と依存関係

- 管理URIで全migrationとRBAC・初期管理者seedを適用。ローカルDBのデータは移していない。初期パスワードはGit管理外の `.env.portfolio-admin.local` に所有者専用の権限で保存し、Vercelには登録していない。
- `scripts/verify_portfolio_web.py` でログイン、Secure/HttpOnly Cookie、BFFの内部ヘッダー上書き、CSRFなしの更新拒否、画像の署名付きアップロード・完了・取得、画像の復元、ログアウト後の401、ログイン制限429/Retry-Afterを確認。
- 直接APIは共有キーなしで403、正しい共有キーでもSwagger/ReDoc/OpenAPIは404。S3の匿名・不正署名による取得も拒否。
- 公開前の監査に基づきNext.jsを16.3.8、Mermaidを11.16.1、FastAPIを0.142.2、Starletteを1.7.0、PyJWTを2.15.1などへ更新。2026-10-04時点の本番依存は `npm audit --omit=dev` と `pip-audit` の既知脆弱性0件。開発用CLI・コード生成ツールを含むnpm全体には35件の指摘が残り、本番依存の結果とは区別する。

```bash
uv run --project ../syncnesto-backend python scripts/verify_portfolio_web.py
```

検証は初期管理者の画像を一時変更してデフォルトへ戻す。既に独自アバターを設定した場合は実行を拒否する。レート制限検証で使う専用IPは同じ1分内に再実行しない。

## 運用上の制限

- S3 bucket CORS/lifecycle APIは非対応。プラットフォームのCORS応答を実通信で確認し、1日以上古い `pending-uploads/` の手動清掃スクリプトを用意。自動清掃は未設定。詳細は [ストレージ設定](supabase-storage-setup.md)。
- Neon FreeではIP Allowが使えず、DBへの接続試行そのものは遮断できない。TLS・認証・権限で守る。資格情報が漏えいした場合は読み書きの被害を防げないため、ロールのパスワードを更新する。
- IP制限はPostgreSQLで共有し、HMAC化したIPを保存する。同一プロセス内の事前制限も併用する。DDoS・分散攻撃・無料枠の消費を完全に防ぐものではない。Vercelには標準のDDoS保護があるが、カスタムWAFルールは作成していない。

## 公式資料

- [Neon IP Allow](https://neon.com/docs/introduction/ip-allow)
- [Neonロールと権限](https://neon.com/docs/manage/roles)
- [Neon Scale to Zero](https://neon.com/docs/introduction/scale-to-zero)
- [Vercelのリクエストヘッダー](https://vercel.com/docs/headers/request-headers)
- [Vercel DDoS保護](https://vercel.com/docs/security/ddos-mitigation)
