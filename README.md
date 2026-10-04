# syncnesto-infra

Syncnestoのローカル開発環境と、無料プランの公開環境を管理します。
公開URL: [Syncnesto](https://syncnesto.vercel.app/login)。

## 構成

```text
terraform/
├── localstack/       # ローカルのS3・SQS（ローカルstate）
├── vercel/           # Next.js・FastAPI・公開ドメイン、連携するNeonプロジェクト
│   └── runtime/      # VercelバックエンドのDB・Supabase S3接続設定
└── neon/             # Neon上のアプリ用DBロール・最小権限
scripts/
└── deploy/           # 公開環境の操作CLIと共通処理
localstack/
└── init/ready.d/     # 起動時のローカル初期リソース作成
tests/                # 認証情報・CLI・CI制約の回帰テスト
```

Terraformの適用順は **vercel → neon → runtime**。
Vercel構成が作るNeonプロジェクトの接続情報をneon構成へ渡し、制限付きアプリ接続をruntimeへ渡します。
CLIが必要なoutputをメモリ内で取得するため、接続URIを引数やtfvarsへ書きません。
Terraform資源のアドレス・共有stateのschemaは維持しています。
登録名はVercelフロントとNeonが `syncnesto`、Vercelバックエンドが `syncnesto-api`、Neon Computeが `production` です。

運用に必要な情報はこのREADMEに集約します。`docs/` はローカルのメモ用で、Git管理しません。

## 前提・検証

- Docker Compose（LocalStack用）
- Terraform 1.14以上・2.0未満（Actionsは1.16.4に固定）
- uv（Python・依存関係は `.python-version` / `uv.lock` で管理）
- AWS CLI（ローカルのS3・SQS確認用）

infraルートから実行します。

```bash
uv sync --locked
make help
make check
```

`make check` はformat・lint・Pythonテストと全Terraform構成のvalidate・公開環境のmockテストを実行します。
クラウドの認証情報・本番stateは使いません。Provider lockはmacOS ARM64・Linux AMD64に対応しています。
通常のPython運用コマンドはinfra単独で実行できます。
アプリのmigration・seedだけは隣の `../syncnesto-backend` を使います。

## ローカル開発

```bash
cp .env.example .env
# .envにLOCALSTACK_AUTH_TOKENを設定
make localstack-up
make terraform-init
make terraform-plan
make s3-ls
make sqs-list
```

`docker-compose.yml` はLocalStackを `http://localhost:4566` で起動します。
`terraform/localstack/` のProviderはこのendpointを使い、AWS本体には接続しません。
READY hookが以下を冪等に作成するため、planが差分なしならapplyは不要です。

- S3: `syncnesto-local-app-bucket`、versioning有効
- SQS: `syncnesto-local-app-queue`
- アバター: バケット内の `default-avatar.png`

freemiumでは任意のS3オブジェクト・SQSメッセージの再起動後の永続化を保証できません。
初期資源の再作成とアップロード済みデータの保存は別です。必要なデータは停止前に外部へバックアップしてください。
停止は `make localstack-down`。ローカル資源を削除する場合だけ `make terraform-destroy` を使います。

バックエンドのローカル `.env` は、そのリポジトリの `.env.example` を基準にします。

```env
AWS_REGION=ap-northeast-1
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_S3_ENDPOINT_URL=http://localhost:4566
AWS_S3_BUCKET_NAME=syncnesto-local-app-bucket
```

`test` はLocalStack専用のダミー値です。本番のキーやDB接続を使わないでください。

## 公開環境の設定・環境変数

Vercel Hobby、Neon Free、Supabase Storage Freeを使います。
この構成は無料プランのまま設定を更新します。プランの上限に達した場合は停止・制限に従います。

Actionsの公開設定は `terraform/vercel/production.tfvars.example`。
ローカルはGit管理外の `terraform/vercel/terraform.tfvars` を使います。
`project_name` はクラウドの登録名、`frontend_domain` / `backend_domain` は公開ドメインです。
APIの接続先は `https://syncnesto-api.vercel.app`。登録名とは別のdomain資源で管理します。
本番ドメインはProductionデプロイへ自動割り当てします。

| 設定 | 定義・入力元 | 保存先 |
| --- | --- | --- |
| フロントのBFF・接続先 | `terraform/vercel/frontend.tf` | VercelフロントのProduction |
| APIの認証・Cookie・Host・アップロード方式 | `terraform/vercel/fastapi.tf` | VercelバックエンドのProduction |
| APIのDB・S3接続 | `terraform/vercel/runtime/` | 同上 |
| Actionsのクラウド操作用キー | GitHubのinfra `production` Environment Secrets | 実行時の環境変数 |
| ローカルのAPIキー | export済みの環境変数（`~/.zshrc`等） | `VERCEL_API_TOKEN` / `NEON_API_KEY` / Supabaseキー |
| ローカルのVercel・Neonキーの補完 | `.env.terraform.local` | export済みの値を優先 |
| ローカルのstate接続 | `.env.terraform-state.local` | `PG_CONN_STR`。export済みの値を優先 |
| 初期管理者のログイン資格情報 | `.env.portfolio-admin.local` | seed時に生成、所有者専用 |

秘密の値を `.tf` / tfvars / Gitへ直接書きません。フロントへDB接続・S3キーを渡さず、`NEXT_PUBLIC_` に秘密を設定しません。
DBパスワード・JWT署名キー・BFF共有キーはstateに含まれます。
runtimeのDB URI・S3キーはephemeral入力・write-only登録で、runtime state・planには保存しません。
`sensitive` だけではstateから秘密を除外できません。

設定変更はTerraformで行い、plan/apply後に対象アプリを再デプロイしてください。
Vercel画面で直接変更した場合はTerraformへ反映し、設定のずれを残さないでください。

## 公開環境の更新

```bash
# ~/.zshrcでキーをexportしている場合
zsh -ic 'make deploy-plan'
# planを確認してから適用
zsh -ic 'make deploy-apply'
```

全構成の既存stateを確認し、空state・削除を含むplanを拒否します。
構成単位の操作は以下です。個別applyではTerraformの確認入力を使います。

| 構成 | コマンド |
| --- | --- |
| Vercel・Neonプロジェクト | `make vercel-init` / `vercel-validate` / `vercel-test` / `vercel-plan` / `vercel-apply` |
| NeonのDB権限 | `make neon-init` / `neon-validate` / `neon-test` / `neon-plan` / `neon-apply` |
| 実行時の接続設定 | `make runtime-init` / `runtime-validate` / `runtime-test` / `runtime-plan` / `runtime-apply` |

CLIは `uv run python -m scripts.deploy --help`。
例: `uv run python -m scripts.deploy terraform neon plan -lock-timeout=120s`。

## GitHub Actions・共有state

`.github/workflows/terraform.yml` はPRで認証情報なしの検証を行い、mainへのpushでは本番planを行います。
mainを指定した手動実行で `operation=apply` を選ぶと本番へ適用します。
本番Environmentはmain限定。DBのadvisory lockとGitHub concurrencyで同時更新を防ぎます。
生ログ・state・planをActions artifactへ公開しません。

infraの `production` Environmentに必要なSecrets:

- `TF_STATE_DATABASE_URL`
- `VERCEL_API_TOKEN`
- `NEON_API_KEY`
- `SUPABASE_S3_ACCESS_KEY_ID`
- `SUPABASE_S3_SECRET_ACCESS_KEY`

共有stateは既存Neonの専用DB `syncnesto_terraform` で管理します。
`vercel`・`neon`・`runtime` のschema名は、互換性のため既存の `portfolio_state`・`database_state`・`runtime_state` を使用します。
管理権限のない `syncnesto_tfstate` を使い、アプリロールとのDB接続を相互に禁止します。
接続はNeon directと `sslmode=verify-full`。URIは `PG_CONN_STR` で渡し、backend定義にはschema名だけを記載します。

`bootstrap-state` は既存stateのバックアップ・共有DBへの移行専用です。通常運用では再実行不要です。
ローカルのバックアップはGit管理外の `state-backups/` に所有者専用で保存します。
state DBは同じNeonプロジェクトにあるため、プロジェクト全体を失うとstateも失います。バックアップを安全な場所へ保管してください。
新規アカウントへの初回構築は、既存環境の更新と分けてstate DBのbootstrapを設計する必要があります。

## migration・初期管理者

```bash
make db-migrate
uv run python -m scripts.deploy seed --email '<管理者メール>'
```

管理用 `syncnesto_owner` のdirect接続を使います。ローカルDBのデータは移しません。
seedはRBACと初期管理者を作り、ランダムなパスワードをローカルへ保存します。既存の資格情報を上書きしません。
本番migrationはbackendのActionsにも組み込まれています。infraのapplyではmigration・seedを実行しません。

## Supabase Storage・キーの更新

StorageはSingaporeの非公開バケットを使います。20MiBのファイル上限、600秒の署名URLを設定します。
S3キーはSupabase Dashboardの対象プロジェクトのStorage → S3設定で発行し、
`SUPABASE_S3_ACCESS_KEY_ID` / `SUPABASE_S3_SECRET_ACCESS_KEY` に設定します。
管理API用の `SUPABASE_ACCESS_TOKEN` はバケット準備専用で、S3キーとは別です。

キーを更新する場合はGitHub Secretsとローカルexportを更新し、
`terraform/vercel/runtime/variables.tf` の `credential_version` を増やします。
infraをapply・backendを再デプロイし、新キーで検証してから旧キーを失効させます。

```bash
uv run python -m scripts.deploy storage prepare
uv run python -m scripts.deploy storage cleanup-pending
uv run python -m scripts.deploy storage cleanup-pending --execute
```

`prepare` は初期構築・復旧用です。非公開設定・サイズ上限・デフォルトアバターを更新します。
`cleanup-pending` は1日以上古い一時アップロードの件数確認。`--execute` 指定時だけ削除します。
SupabaseはS3のbucket CORS/lifecycle設定APIに非対応で、CORSは実通信で確認しています。自動清掃は未設定です。

## 実通信の検証・保護の範囲

```bash
zsh -ic 'make verify-state'
make verify-database
zsh -ic 'make storage-verify'
uv run python -m scripts.deploy verify-web --skip-upload
```

- state: TLS・権限分離・Terraformのロック競合を確認します。
- DB: UUID付きの検証テーブルでCRUD・管理操作の拒否を確認し、最後に削除します。
- Storage: 検証オブジェクトで署名付き送受信・匿名拒否・CORSを確認し、最後に削除します。
- Web: ログイン・Secure/HttpOnly Cookie・CSRF拒否・ログアウト・回数制限を確認します。

`verify-web --skip-upload` はアバターを変更しません。
画像アップロードも確認する場合は、デフォルトアバターの初期管理者で `make verify-web`。
画像を一時変更してデフォルトへ復元します。独自アバターなら変更前に拒否します。
回数制限の検証は同じ1分内に再実行しないでください。

アプリDBは `syncnesto_app` のCRUD・sequence利用だけを許可し、DDL・ロール/DB作成・管理権限を禁止します。
APIは共有BFFキーを必須にし、公開ドキュメントを閉じ、本番Cookie・Host・TLS設定を起動時に検証します。
ログイン10回/分・通常240回/分・全体6000回/分の制限をDBで共有します。
Neon Freeでは接続試行自体のIP遮断はできません。TLS・認証・権限分離で保護し、攻撃を完全に遮断する保証はありません。
