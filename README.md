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

### ローカルの承認メール

Mailpitにメールを受け取り、本人確認リンクをブラウザで操作します。Mailpitは外部のメールアドレスへ配送しません。
以下はMailpitだけを起動するため、起動中のLocalStackや別ComposeのPostgreSQLを再起動しません。

```bash
make mailpit-up
```

受信画面は [http://localhost:8025](http://localhost:8025)。SMTPは `127.0.0.1:1025` です。
両ポートはホストのloopbackだけに公開します。受信メールは専用の `mailpit_data` volumeに保持し、停止は `make mailpit-stop`。
500通を超えると古いメールから削除します。確認リンクは本人確認用の秘密を含むため、受信画面を外部へ公開しないでください。

ホスト上で動かすBackendのGit管理外 `.env` に次の設定を追加して再起動します。
`FRONTEND_PUBLIC_URL` は実際に利用するFrontendのoriginに合わせてください。

```env
EMAIL_PROVIDER=smtp
EMAIL_FROM=Syncnesto <noreply@syncnesto.local>
FRONTEND_PUBLIC_URL=http://localhost:3000
EMAIL_TIMEOUT_SECONDS=10
SMTP_HOST=127.0.0.1
SMTP_PORT=1025
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_STARTTLS=false
```

Backendを同じComposeネットワーク内で起動する場合は `SMTP_HOST=mailpit` にします。
この設定では `admin@example.com` 等の開発用メールもMailpitで受け取れます。
`EMAIL_PROVIDER=disabled` が未設定時の既定で、送信できない場合は資格情報を変更しません。

### ドメイン購入なしでGmailから実送信する

指定された送信用アドレスは `syncnesto@gmail.com` です。無料Gmailアドレスを使うと、独自ドメインの購入なしで承認メールを送れます。
このアカウントの準備・所有と実送信は別途確認します。
送信用Googleアカウントの2段階認証を有効にし、[Syncnesto専用アプリパスワード](https://support.google.com/accounts/answer/185833?hl=ja) を作成してください。
通常のGoogleログインパスワードは使いません。アプリパスワードを作れない保護設定・組織アカウントもあります。

BackendのGit管理外 `.env` へ、Mailpit設定の代わりに以下を設定して再起動します。
パスワードをチャットやGitへ貼らず、画面上の区切り空白を除いた16文字を設定します。

```env
EMAIL_PROVIDER=smtp
EMAIL_FROM=Syncnesto <syncnesto@gmail.com>
FRONTEND_PUBLIC_URL=http://localhost:3000
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=syncnesto@gmail.com
SMTP_PASSWORD=<空白なし16文字の専用アプリパスワード>
SMTP_STARTTLS=true
```

送信元は認証したGmailアドレスと同じにします。STARTTLSの証明書検証に失敗した場合は認証・送信しません。
実送信テストには実際に受信できるアドレスを使用し、Mailpitで確認するときは前節の設定へ戻してください。
Gmailには [送信上限](https://support.google.com/mail/answer/22839?hl=ja) があり、小規模運用を想定しています。
Googleのログインパスワード変更時はアプリパスワードも失効するため、再発行・環境変数更新が必要です。

本番は `FRONTEND_PUBLIC_URL` をHTTPSのFrontend originへ変更し、BackendだけにSMTP変数を登録します。
本番SMTPは `smtp.gmail.com:587`、STARTTLS、認証、送信元一致を必須にしています。
SMTPパスワードは既存runtimeと同様にTerraformのephemeral入力・write-only登録で管理し、Frontendへ渡しません。
[Vercelでは587番のSMTP接続が許可されています](https://vercel.com/kb/guide/serverless-functions-and-smtp) が、Python Runtimeでの送信・背景処理・到達はpreview環境でも検証してください。
2026-10-04にローカルBackendのGmail資格情報をGit管理外で設定し、TLS接続・SMTP認証・確認メール1通の送信・ユーザーによる受信確認を完了しました。本番メール環境変数の適用とVercelからの実送信は未実施です。
Backendの確認フロー・SMTP/SES切り替え方針は [email-approval.md](../syncnesto-backend/docs/email-approval.md) を参照してください。

### 将来のResendへの切り替え

2026-10-04時点の [Resend Free](https://resend.com/pricing) は3,000通/月・100通/UTC日・認証済み3ドメインです。
Resendは [Vercel Marketplace](https://resend.com/docs/guides/vercel-marketplace-integration) から利用できますが、この統合はVercelで購入した独自ドメインが前提です。
独立したResendアカウントとAPIでは、別のレジストラで取得した所有ドメインも使えます。
現在の `syncnesto.vercel.app` は送信ドメインとして使えません。

独自ドメインを [認証](https://resend.com/docs/add-a-domain) した後、Backend専用に `EMAIL_PROVIDER=resend`、`EMAIL_FROM`、`RESEND_API_KEY` とHTTPSの `FRONTEND_PUBLIC_URL` を設定します。
APIキーは `NEXT_PUBLIC_` に設定せず、Terraformの既存runtimeと同様にephemeral入力・write-only登録で管理してください。
本番の送信設定・DNS・APIキー・Terraform/Actionsの切り替えは、ローカル確認後に行います。現構成は本番にメール関連変数を登録していません。

独自ドメインがない段階では、`onboarding@resend.dev` から [Resend登録本人への試験送信](https://resend.com/docs/knowledge-base/403-error-resend-dev-domain) に限られます。
一般利用者への承認メールには独自ドメインが必要です。`admin@example.com` のような開発用アドレスをResendの実送信検証には使わないでください。
将来SESへ移す場合は送信アダプターを追加し、本人確認・権限・監査は共用します。

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

Frontend/Backendの本番公開は、それぞれのActionsでCIを通過した後に行います。
Vercel側にGit接続が残っていると、main更新でCI・migrationより先に公開されるため、
各Projectの接続先を確認してGit自動デプロイを解除してください。
`connect_github=false`の設定だけで、既存のGit接続が解除されたとは判断しないでください。

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

マルチテナント移行後は、指定した既存IdentityだけをDefault Tenantの初期Ownerにします。既存の別Ownerがいる場合は処理を拒否します。

```sh
uv run python -m scripts.deploy tenant-owner --email '<指定Ownerメール>'
# 初期パスワードも明示的に設定する場合だけ、0600のファイルを指定する
uv run python -m scripts.deploy tenant-owner --email '<指定Ownerメール>' --password-file '<絶対パス>'
```

このコマンドはRBACとOwnerを初期化し、Project所属を保持します。パスワード指定時は対象本人の既存セッションを失効します。バックアップ・移行・対応Backend/Frontendの公開順序は [組織境界と移行手順](../syncnesto-backend/docs/multi-tenancy.md) を参照してください。

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
本番migration・seed・Owner初期化ではメール送信を無効にし、Terraformの公開Frontend URLを使います。
Backendの開発用`.env`にSMTPやlocalhostの設定があっても、運用処理には引き継ぎません。
APIは共有BFFキーを必須にし、公開ドキュメントを閉じ、本番Cookie・Host・TLS設定を起動時に検証します。
ログイン10回/分・通常240回/分・全体6000回/分の制限をDBで共有します。
Neon Freeでは接続試行自体のIP遮断はできません。TLS・認証・権限分離で保護し、攻撃を完全に遮断する保証はありません。
## ポートフォリオ用デモへの切り替え

`terraform/vercel`の`app_env`は既定`production`で、デモは自動で有効にしない。
専用DB・制限付きruntime role・専用非公開バケットを準備し、`runtime`の接続先を設定した後、
`app_env = "demo"`と`demo_data_isolated = true`を設定する。
このフラグは実際のバケット・DB分離の検査や資源作成を行わないため、設定確認を省略しない。
FrontendとBackendのAPP_ENVを合わせ、Backendのメールを無効にし、BFFとは別のCRON_SECRETを使う。
Backend CIは取得したAPP_ENVに応じて日次Cron設定を追加する。
通常環境のCronは既定で登録しない。ローカル検証はmock planを使用し、cloud applyは別のリリース作業とする。

## 通常データの30日保持後の定期回収

`terraform/vercel` の `deleted_data_cleanup_mode` は既定 `disabled`。
通常環境だけで `deleted_data_cleanup_tenant_ids` を明示し、まず `dry_run` で対象確認する。
候補・監査結果を確認後に `execute` へ変更する。Demoとの併用と対象未指定をplan時に拒否する。
既存のBackend専用 `CRON_SECRET` を使い、Frontendには回収設定・秘密を渡さない。

Backendのデプロイ設定生成がmodeに応じて `/internal/trash/cleanup` の日次Cronを登録する。
保持期間はBackendの既定30日、全組織合計の上限20資源・時間予算20秒。
上限は `deleted_data_cleanup_limit`（1〜100）、予算は `deleted_data_cleanup_budget_seconds`（1〜40）で指定する。
時間予算は実行中の処理を中断する厳密な期限ではない。残件は次回または既存の手動CLIで回収する。
設定・失敗時の再試行・結果確認は [Backendの運用手順](../syncnesto-backend/docs/deleted-data-cleanup.md) を参照。
この変更ではcloud apply・Productionの回収モード有効化・実データ削除を行わない。
