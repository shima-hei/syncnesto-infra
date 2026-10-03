# ポートフォリオ公開環境

このTerraformはVercelのNext.js・FastAPIプロジェクトとNeonのPostgreSQLを作成する。LocalStack用の `terraform/` とはProvider・stateを分離している。オブジェクトストレージはSupabase Storage Freeを使用する。バケット・S3キー・初期seed・実デプロイは準備完了後に行う。

## 作成内容

- Vercel: Node.js 22のNext.jsプロジェクト。ProductionのBFF・Cookie設定。Previewの自動デプロイは無効。
- Vercel: FastAPIプロジェクト。Singapore、Fluid Compute、実行上限60秒。ProductionのJWT署名キー・共有キー・Cookie設定。GitHub未接続。
- Neon: PostgreSQL 17、`production` ブランチ、`syncnesto` DB、`syncnesto_owner` ロール、read-write compute。0.25 CU固定・5分の無操作で停止・履歴保持6時間。
- `database/`: 管理ロールと別の `syncnesto_app`。テーブルのSELECT/INSERT/UPDATE/DELETEとシーケンス使用だけを許可し、DDL・ロール/DB作成を禁止する。今後のmigrationで管理ロールが作るテーブルにもdefault privilegesを適用する。
- `runtime/`: 制限付きDB接続とSupabase S3の資格情報をバックエンド専用のSensitive環境変数として登録。秘密はephemeral入力・write-only値で渡す。
- 接続先: 既定はSingapore（Neon `aws-ap-southeast-1`、Vercel `sin1`）。FastAPIも同地域で運用する想定。

アカウントはVercel Hobby・Neon Freeを使う。Terraformはプランの変更や課金サービスの追加をしない。無料枠を超えたときの停止・制限は各サービスのFree/Hobbyプランに従う。Neon ProviderはNeon公式資料で紹介されているコミュニティ製 `kislerdm/neon` を利用する。

## 1. 設定・認証

Terraform 1.14以上（2.0未満）とPython 3を使う。以下はinfraルートから実行する。

```bash
cp terraform/portfolio/terraform.tfvars.example terraform/portfolio/terraform.tfvars
cp .env.terraform.local.example .env.terraform.local
chmod 600 .env.terraform.local
```

`terraform.tfvars` には確認済みの `shima-hei` チームとNeonのFree組織のIDを設定している。別アカウントで実行する場合は両IDを変更する。名前・地域を変更するなら最初のapply前に行う。

`.env.terraform.local` に `VERCEL_API_TOKEN` と `NEON_API_KEY` を設定する。Vercelトークンは対象チームのプロジェクト管理権限、Neonキーはプロジェクト作成権限が必要。

Makeコマンドは専用ファイルを読み、値を表示せずTerraformへ渡す。すでにexport済みの変数があればそれを優先する。`~/.zshrc` でexportしている場合は `zsh -ic 'make portfolio-plan'` のように対話シェル経由で実行できる。LocalStackの `.env` は読み替えない。

APIトークン・個別のtfvars・state・planはGit管理外。stateにはNeonが発行したDBパスワード・接続URIが含まれるため、安全な場所に保管する。`sensitive` は表示を隠す指定であり、stateを暗号化するものではない。

## 2. プロジェクト・DBの作成

初回は `connect_github = false`、`backend_api_url = null` のまま実行する。この段階ではGitHubを接続せず、Webサイトの自動デプロイは始めない。

```bash
make portfolio-init
make portfolio-validate
make portfolio-test
make portfolio-plan
make portfolio-apply
```

planでVercelプロジェクト、Neonプロジェクト（ブランチ・compute・DB・ロールを含む）、Vercel環境変数の作成だけになっていることを確認する。applyはTerraformの確認入力を求める。認証情報を引数やtfvarsには書かない。

`terraform/portfolio/.terraform.lock.hcl` はGitで管理する。Provider更新は変更内容とplanを確認してから行う。

## 3. DBの権限設定

プロジェクト作成後、別stateのDB権限を適用する。ヘルパーが管理資格情報を最初のstateからメモリ内で読み、環境変数としてProviderへ渡す。管理パスワードの変数はephemeralでplan・このstateに保存しない。接続には証明書とホスト名の検証を必須とする。

```bash
make database-init
make database-validate
python3 scripts/portfolio_terraform.py database test
make database-plan
make database-apply
```

実通信の再検証はinfraルートから以下で実行する。UUID付きの検証テーブルを作成し、通常の読み書き・禁止操作・TLS・不正パスワードを確認して削除する。既存テーブルを操作しない。資格情報を表示しない。

```bash
uv run --project ../syncnesto-backend python scripts/verify_portfolio_database.py
```

## 4. FastAPI側の準備

Neonの接続URIは認証情報を含むため、通常のoutputでは隠れる。

```bash
terraform -chdir=terraform/portfolio/database output -raw backend_database_url
terraform -chdir=terraform/portfolio output -raw migration_database_url
terraform -chdir=terraform/portfolio output -raw backend_bff_secret
```

これらの `-raw` コマンドは秘密を表示するため、共有画面・ログでは実行しない。通常はヘルパーがメモリ内で値を受け渡す。FastAPIの `DATABASE_URL` は `database/` の制限付きpooled URI、Alembicの `DATABASE_URL` は管理用direct URIを使う。両方 `sslmode=verify-full` を指定する。PythonはOSのCAファイル、存在しなければcertifiを使い、必要なら `PGSSLROOTCERT` を設定する。管理URIとDB資格情報をフロントエンドや `NEXT_PUBLIC_` 変数へ渡さない。

アプリのmigrationは次のコマンドで管理URIを使って適用する。ローカルのデータやseedは移さない。

```bash
make portfolio-migrate
```

Supabaseの確認・S3キー発行・runtimeの適用手順は [ストレージ設定](../../docs/supabase-storage-setup.md) を参照する。

FastAPIはHTTPSで公開し、少なくとも以下を設定する。その他の必須設定はバックエンドの `.env.example` とREADMEに従う。

```env
APP_ENV=production
ALLOWED_HOSTS=<実際のFastAPIホスト名>
# Terraformのbackend_bff_secretをホストの秘密設定へ登録する。
BFF_SHARED_SECRET=<秘密の値>
AUTH_COOKIE_SECURE=true
CSRF_COOKIE_SECURE=true
ALLOW_BEARER_TOKEN_RESPONSE=false
ALLOW_AUTHORIZATION_HEADER=false
FILE_UPLOAD_MODE=presigned
```

本番用の `SECRET_KEY` はTerraformで生成・登録する。初期管理者設定、非公開S3バケット・接続設定も必要。SupabaseはAWS向けのbucket CORS/lifecycle APIに対応しないため、実際のCORS応答と `pending-uploads/` の清掃運用を別途確認する。詳細はストレージ設定とバックエンドの `docs/frontend-file-upload.md` を参照。

`SECRET_KEY` は32文字以上のランダム値を使う。本番では共有キー不足、安全でないCookie、Bearer認証、ワイルドカードHost、TLS検証のないDB URI、SQLログを起動時に拒否する。APIドキュメントは閉じる。ログイン10回/分・その他240回/分のIP制限をPostgreSQLで共有し、再起動・複数instanceをまたいで維持する。全体6000回/分でカウンター増加も制限する。カウンター確認に短い独立DBトランザクションを使い、障害時は503を返す。

Neon FreeはネットワークのIP Allowを利用できず、DBの接続先は公開される。TLS・強い認証情報・実行ロールの権限分離で保護する。認証情報の漏えいを防ぐ必要があり、接続試行や全ての攻撃を遮断する保証はない。確認範囲と公開前の残作業は [セキュリティ確認](../../docs/portfolio-security.md) を参照。

## 5. フロントエンドの接続

まず `connect_github = false` のまま `backend_api_url` にFastAPIの実際のHTTPS originを設定し、plan・applyする。VercelにProductionの `API_BASE_URL` が登録されたことを確認する。

その後 `connect_github = true` に変更し、再度plan・applyする。GitHubを接続する際はVercel GitHub Appに `shima-hei/SyncNesto-frontend` の参照権限が必要。`main` へのpushがProduction deploymentを作成する。設定を変更しても既存deploymentへ環境変数は反映されないため、再デプロイする。

ポートフォリオのProductionはVercelログイン不要とし、アプリ内の既存認証を利用する。Previewは自動作成せず、ProductionのAPI・DBを共有しない。Previewを追加する際は別のNeonブランチとバックエンドを用意する。

## 検証と削除

`make portfolio-test` はProviderをmockしたplanテスト。バックエンド未準備でのGitHub接続拒否、HTTPS originの検証、Production接続先、DB認証情報をフロントへ渡さない設定を確認する。リモートの認証・プラン制約・実際のデプロイ成功は `plan` / `apply` と実通信で別途確認する。

両プロジェクトには `prevent_destroy = true` を設定している。名称・Neon地域など、置き換えが必要な変更はplanで停止する。削除はDBバックアップを取った上で、この保護を明示的に外して行う。Terraform設定自体の削除は保護を回避するため、stateと設定を保持する。

## 参照

- [Vercel Provider](https://registry.terraform.io/providers/vercel/vercel/latest/docs)
- [Neon Terraform](https://neon.com/docs/reference/terraform)
- [Neon料金・無料枠](https://neon.com/pricing)
- [Neon接続方法](https://neon.com/docs/connect/connection-pooling)
