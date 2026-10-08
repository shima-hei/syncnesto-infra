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

`terraform/vercel`の`app_env`は`production`のみを許可する。`demo_mode`は既定falseで、デモは自動で有効にしない。
専用DB・制限付きruntime role・専用非公開バケットを準備し、`runtime`の接続先を設定した後、
`app_env = "production"`を維持し、`demo_mode = true`と`demo_data_isolated = true`を設定する。
このフラグは実際のバケット・DB分離の検査や資源作成を行わないため、設定確認を省略しない。
FrontendとBackendへ`APP_ENV=production`と`DEMO_MODE=true`を渡し、Backendのメールを無効にし、BFFとは別のCRON_SECRETを使う。
Backend CIは`APP_ENV=production`を検証したうえで、取得したDEMO_MODEに応じてデモの日次Cron設定を追加する。
デモと通常のごみ箱回収は併用しない。デモ無効の場合だけ、明示した通常回収設定からごみ箱Cronを生成する。

2026-10-08に、提案と実装の不一致を修正し、実行環境とデモ機能を分離する方針へ戻した。
決定・変更・検証記録の正はBackendの`docs/decisions/2026-10-08-demo-mode.md`とする。
旧`app_env = "demo"`は検証エラーとなるため、`production`へ戻して`demo_mode`を明示する。
migration・seedなどの運用コマンドは`DEMO_MODE=false`を明示し、デモ用runtime設定を引き継がない。
通常環境のCronは既定で登録しない。ローカル検証はmock planを使用し、cloud applyは別のリリース作業とする。

### デモ専用資源の分離準備（2026-10-08）

状態: 配置案はユーザー承認済み。専用構成と操作コマンドのローカル実装・検証を完了。
cloud apply・環境変数変更・デプロイは未実施。
ユーザー指示に従いローカルコミットまでとし、pushは保留する。
`APP_ENV=production` / `DEMO_MODE=true` の方針は変更しない。

#### 現構成の確認結果

| 対象 | 確認した状態 |
| --- | --- |
| Neon | `misty-band-66896279` / `br-green-flower-azgbl4jk`（production）、PostgreSQL 17、Free `free_v3` |
| 業務DB | `syncnesto`、revision `48bb3c9773b3`、User 1・Tenant 1・Project 0・DemoSession 0 |
| DB権限 | runtimeは`syncnesto_app`。superuser / create DB / create role / bypass RLSなし。管理用ownerと分離 |
| Terraform state | 既存Neon内の`syncnesto_terraform`、専用`syncnesto_tfstate`。業務DBと別DB |
| Supabase | `pdyywnoregglnyjlapta`、`ap-southeast-1`。接続から見えるProjectは1件 |
| バケット | `syncnesto-portfolio`、private、1ファイル20MiB上限。2オブジェクト、合計1,104,355 bytes |
| Vercel | Backendの`APP_ENV=production` / `FILE_UPLOAD_MODE=presigned`、S3 endpointとbucketは上記を参照 |
| デモ設定 | Backend・FrontendのProduction環境変数に`DEMO_MODE`なし。専用資源は未作成 |

DBは集計とrole属性、Storageはバケット設定と件数・容量、Vercelは非秘密設定と秘密の存在・種別だけを確認した。
Userのメール、DBパスワード、S3キー、JWT/BFF秘密、署名URL、オブジェクト本文はこの記録に保存しない。
Vercelの`sensitive`な`DATABASE_URL`は復号していない。DB接続先はTerraformの管理情報を確認したもので、
公開runtimeがその値を使用していることの最終確認は切り替え時の実通信で行う。

#### 分離する資源

1. **Neonに空の新規Project `syncnesto-demo`を作る**。既存のproduction branchやstate DBの複製は行わない。
   同じOrganization `org-empty-dew-85265327`、同じSingapore regionを候補とし、PostgreSQL 17、compute 0.25 CU、
   Freeの自動停止と6時間の履歴保持を維持する。実際のID・hostは作成後に記録し、既存IDを推測で流用しない。
2. 新しいDBにも既存と同じ`syncnesto_owner` / `syncnesto_app`の権限分離を適用する。
   資格情報は新規生成し、runtimeはpooler、migration・検証・backupはdirect接続、いずれも`sslmode=verify-full`を要求する。
   runtimeにowner URI・Terraform state接続・クラウド管理トークンを渡さない。
3. **Supabaseにも別Project `syncnesto-demo`とprivate bucket `syncnesto-demo`を作る**。
   2026-10-08に既存Organization `shima-hei`（`yxsnqlgubcohdavdcpry`）での作成をユーザーが承認した。
   Singapore regionを使用する。作成前の費用確認は別途行い、課金を伴う作成はしない。
   新しいProject専用S3キーを使い、既存Projectのキー・オブジェクトを持ち込まない。
   バケット側も1ファイル5MiBを上限にし、既存の5MiBのデモ制限と揃える。
4. `default-avatar.png`だけをリポジトリの静的ファイルから用意する。利用者が書くファイルは`demo/<UUID>/`配下に限定する。
   Backendの既存S3互換APIとpresigned方式、Frontendのupload planを継続する。
5. Vercelの既存2プロジェクトと公開URLは維持する。専用資源を検証した後に接続先を切り替える。
   既存DB・Storage・stateは保持し、通常データの削除や既存Projectの置き換えをplanに含めない。

Supabaseの静的S3 access keyは、同じProject内の**全バケットに全S3操作を許可し、RLSを迂回する**。
別バケットだけでは、漏えいしたデモ用キーから既存Storageを保護できないため、Projectも分離する。
JWTによるStorage RLSへ移行する方式は、現在のFastAPI認証とS3構成を変更するため今回の案には含めない。
この分離はアプリのDB/S3資格情報の到達範囲を限定するもの。Organization管理トークンは別途、運用側で保護する。
根拠: [Supabase S3 Authentication](https://supabase.com/docs/guides/storage/s3/authentication)。

#### 無料枠と容量

- Neonの現在の公式料金表はFreeが100 Projects、1 Projectあたり100 CU-hours/月・Postgres 1GB、
  全ProjectのPostgres合計20GB、5分無操作で停止と案内している。既存ProjectのAPI上限も1GiBだった。
  過去の0.5GBという資料を現行上限として使わない。作成時には対象Organizationと新Projectの実際のプラン・上限を再確認する。
  [Neon Pricing](https://neon.com/pricing.md)、[Neon Plans](https://neon.com/docs/introduction/plans.md)。
- Supabaseの公式Freeはactive Projects最大2件、file storage 1GB、1週間無操作でpauseとなる。
  接続から見える1件だけで、アカウント全体の残枠やOrganizationの料金を確定しない。
  課金なしで作成できることを確認できなければ作成を止め、有料化・枠の迂回をしない。
  [Supabase Pricing](https://supabase.com/pricing)。
- 現在のデモは未回収も含め全体10件、1デモ10ファイル予約・合計20MiB、1件5MiB。
  論理予約の合計は最大200MiBだが、確定前の一時キー・遅延PUT・コピー中の重複は物理容量と別に評価する。
  DBは1デモ500業務行・Project 3件・一時User 10人。行数制限だけでDBの実容量や月間転送量は保証しない。
- 公開前にDB実容量、Storage実容量、未回収件数、回収失敗、利用量上限を確認する手順を用意する。
  無料枠の超過・pauseは体験の可用性を下げるため、デモの継続運用に含めて扱う。
  新しい定期監視や有料サービスはこの準備作業では作成しない。

#### IaCと初期化の変更点

- 現在の`neon_project.portfolio`と`portfolio_state` / `database_state` / `runtime_state`は維持する。
  `project_name`の書き換えで既存Projectをデモ用に転用しない。
- デモのNeon資源・runtime roleには独立した構成とstate schema（`demo_resources_state` / `demo_database_state`）を用意する。
  state自体は運用側の既存`syncnesto_terraform`に置き、デモ業務DBへstateを複製しない。
  新stateの初回構築と既存stateの更新を分け、既存CIの「空state拒否」を外さない。
- Vercelの環境変数は既存のstateで一元管理する。別stateから同じ環境変数を重複管理しない。
  `runtime_state`への入力元だけを明示的に選択できるようにする。
  現在の`terraform` / `migrate` / `seed` / `verify-database`は既存Neonのoutputを読むため、
  デモ用のtargetを明示し、旧host / Project / bucketを拒否してから実行する経路が必要。
- `scripts/deploy/storage.py`は既存Project・bucketが固定されている。デモのprepare/verify/cleanupに流用せず、
  Project・bucket・region・originを明示する経路を追加する。既存のprepareやcleanupをこの準備では実行しない。
- 新DBはAlembicで構築し、`seed_roles_and_permissions`の既存処理を再利用してRBACだけを作る経路を追加する。
  現行`seed_rbac` / Infraの`seed`は初期system_adminも作るため、そのまま実行しない。
  既存migrationが作る空のDefault Tenantと共通Roleは許容し、User・通常ログイン用管理者・業務データは作らない。
  サンプルはデモ開始時に既存`DemoService`で生成する。既存Alembic履歴や認可モデルは変更しない。
- `DEMO_DATA_ISOLATED=true`は運用上の確認宣言であり、資源ID・接続先・キーの分離を自動検査しているわけではない。
  flagだけで公開せず、Project ID、DB host、runtime権限、private bucket、鍵の所属を確認した記録を残す。
- Backendの`MIGRATION_DATABASE_URL`、Infra CIのDB/S3入力元とProduction用tfvarsも切り替え対象になる。
  手元の変更だけで運用し、次のCIで既存接続先や`demo_mode=false`へ戻る状態を作らない。

#### 切り替えと戻し方

1. 新規資源の作成先・無料枠・費用を確認し、専用資源だけを作成する。
   ID・host・bucket・roleと配置を秘密なしの一覧へ追記し、作成planに既存資源の削除・置き換えがないことを確認する。
2. 新DBへmigrationとRBACのみのseedを行い、User 0・Project 0・通常管理者なしを確認する。
   新roleのCRUD・DDL拒否・TLS、新bucketの非公開性・presigned PUT/GET・CORS・サイズ拒否を検証する。
   検証用オブジェクトは専用prefixに限定して回収する。
3. pushが許可された後に`DEMO_MODE`修正とデモ準備コードをCIで検証する。
   本番移行前に既存DB・stateと非秘密設定の一覧を所有者専用でbackupし、秘密の戻し先を安全に確保する。
   新DBのdirect URIとruntime pooler URIが同じ専用Projectを参照することを確認する。
4. 短い切り替え時間を設け、Backend→Frontendの順に公開する。新DB/S3キーと専用JWT署名キー・BFFキー・Cron秘密を使う。
   JWTを分け、通常環境のCookieをデモDBで受け付けない。BFFキーの変更は両方のデプロイに揃える。
   `APP_ENV=production`、両方の`DEMO_MODE=true`、Backendの`DEMO_DATA_ISOLATED=true`、
   `EMAIL_PROVIDER=disabled`、`DELETED_DATA_CLEANUP_MODE=disabled`を設定する。
   接続先・環境変数変更は再デプロイ後の動作まで確認し、旧deploymentとの一時的不整合も切り替え時間に含める。
5. 公開URLで2人の別デモ、要件・タスク・テスト・ドキュメント、組織管理、5MiB以下の添付を確認する。
   他デモ参照・運営権限・通常Cookieを拒否すること、ログアウト・idle/absolute失効・リセットのアクセス失効、
   業務行・User・ファイルと遅延PUTの最終回収、Cron認可と再試行を確認する。
6. 戻す場合はデモ受付を止め、両方の`DEMO_MODE=false`、旧DB/S3接続先と対応する旧秘密・CI入力を復元して再デプロイする。
   環境変数だけを戻したり、旧deploymentだけをpromoteして完了としない。
   デモDBを通常DBへコピーせず、デモの回収は専用接続先で継続し、回収確認前に新資源を削除しない。
   受付停止やデモ無効化だけでは物理回収は実行されない。回収APIを維持できない場合の専用CLIは公開前に用意する。

ログアウト・失効時のアクセス拒否と物理削除の完了時刻は区別する。
現行のCronは日次で、ブラウザを閉じた後の物理回収・障害再試行・発行済みPUTの最終回収が遅れる場合がある。
Neonの履歴・所有者専用backupに残るデータの即時消去も保証しない。
「終了と同時に全媒体から完全削除」とは案内せず、体験終了後にアクセスを失効し、回収を再試行する現在の仕様を維持する。

#### 専用資源の操作コマンド

`terraform/demo`は空のNeon Projectと独立したJWT/BFF/Cron秘密、`terraform/demo-neon`は既存と同じ制限付きroleを扱う。
既存のrole構成・resource addressは変更せず、デモ用の接続先検査を追加した別stackにした。
通常のCIが実行するstackは従来の3つに限定し、追加のデモstackを自動applyしない。
`make check`のローカル検証にはデモの2構成も含める。

費用・無料プラン確認と既存stateのbackupが終わってから、以下を実施する。
`init`は共有stateに専用schemaを作るため、この準備段階では実行していない。
`free_plan_confirmed`は確認宣言であり、Neonの請求情報を自動検査する機能ではない。

```sh
uv run python -m scripts.deploy terraform demo init -input=false -lockfile=readonly
uv run python -m scripts.deploy terraform demo plan -input=false -var=free_plan_confirmed=true -out=demo.tfplan
# planの新規資源だけを確認してからapply。生のplan・stateを公開しない。
uv run python -m scripts.deploy terraform demo apply -input=false demo.tfplan

uv run python -m scripts.deploy terraform demo-neon init -input=false -lockfile=readonly
uv run python -m scripts.deploy terraform demo-neon plan -input=false -out=demo-neon.tfplan
uv run python -m scripts.deploy terraform demo-neon apply -input=false demo-neon.tfplan

uv run python -m scripts.deploy demo migrate
uv run python -m scripts.deploy demo seed
uv run python -m scripts.deploy demo verify-database
```

`demo`コマンドは専用stateを読み、通常Project ID・DB host・異なるpooler・state DB・TLS未検証URIを拒否する。
`demo seed`はUser・Project・DemoSessionが0件であることを確認し、Backendの`seed_rbac --roles-only`だけを呼ぶ。
通常の`seed`では従来どおり初期管理者を作る。API契約・DBモデル・Alembic履歴は変更しない。
運用用Backend subprocessは`APP_ENV=production` / `DEMO_MODE=false` / メール無効で動かし、
Terraform state・クラウド管理トークンを子プロセスへ渡さない。

Storage Projectを費用確認後に作成し、専用S3キーを`.env.demo.local`またはexportした環境変数へ設定する。
ファイルを使う場合は`.env.demo.local.example`を参考にし、所有者専用の`chmod 600`を必須とする。
通常のS3キーへのfallbackをせず、通常Project refや通常キーの再利用を拒否する。
prepare/verify前には管理APIで承認済みOrganization・Project名・region・稼働状態を確認し、
指定S3 endpointでキーが認証できることを読み取りで確認する。

```sh
# SUPABASE_ACCESS_TOKENは管理APIでの所属確認用に環境へexportする。
uv run python -m scripts.deploy demo storage prepare
uv run python -m scripts.deploy demo storage verify

# Vercelのデモ受付を止めた後も、専用DB・Storageだけを対象に確認/回収できる。
uv run python -m scripts.deploy demo cleanup
uv run python -m scripts.deploy demo cleanup --execute
```

回収は標準でdry-run、`--execute`で既存`DemoService`の期限切れ・所有範囲・再試行処理を使う。
一回最大10件。台帳の`cleanup_after`まで待つ遅延PUTや障害分はpending件数に残し、後で再実行する。
通常Identityや業務本文・署名URL・資格情報は出力せず、処理件数と未完了件数だけを表示する。
Vercelの接続先・CI入力・公開用秘密の切り替えは、この準備用コマンドでは行わない。

#### 作業・検証記録

- 2026-10-08: 空のNeon＋別Supabaseという構成と、Supabase Organization `shima-hei`をユーザーが承認。
- Supabase MCPの`get_cost`は、接続先の`tools/list`に提供されておらず利用できなかった。
  ブラウザの[対象OrganizationのBilling](https://supabase.com/dashboard/org/yxsnqlgubcohdavdcpry/billing)で
  Free Plan / Spend cap enabledを確認。新規Project画面のOrganizationも`shima-hei FREE`を確認した。
  Free枠内の追加費用0 USD/月という条件をユーザーへ確認してから資源を作成する。
  APIによる見積もり取得成功とは記録しない。
- Backend: `--roles-only`と専用回収CLIを追加。関連PostgreSQL回帰25件成功（14.93秒、既存警告1件）。
  通常の管理者seed維持、管理者なしのRBAC初期化、デモ無効時のdry-run/回収、既存のデモ境界・容量・破棄を含む。
  ruff / pyright成功。API契約・DBモデルの変更がないためOrval再生成・新migrationは不要。
- Infra: Python単体24件、ruff / format、全6構成のvalidate、模擬plan 21件成功。
  本番CIのstack維持、通常接続先・Storageキーの拒否、private / 5MiBの指定、管理トークンの子プロセス除外を確認。
  新規2構成のProvider lockはmacOS ARM64 / Linux AMD64を固定した。
- `git diff --check`成功。変更は本体のBackend・Infraに別々のローカルコミットへ保存。
- 今回のTerraform初期化は`-backend=false`でProvider検証だけを行った。共有stateのbootstrap/initやcloud applyは実行していない。
  cloud migration/seed・Storage prepare/verify・資源作成・環境変数変更・push・デプロイは未実施。
  クラウドの実通信検証と公開後のライフサイクル確認は、資源作成・公開切り替え後に実施する。

次は、無料作成の確認後に専用資源を作成し、migration・RBAC・runtime role・private Storageを実通信で検証する。
その後にruntime入力元・CI・公開用秘密を切り替える変更へ進む。push・公開切り替えは引き続き保留する。

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
