# GitHub Actionsと共有Terraform state

## stateの保存先

追加サービスを契約せず、既存Neon Freeプロジェクト内の専用DB `syncnesto_terraform` を使う。Terraform標準の `pg` backendで、project・DB権限・runtimeのstateをそれぞれ `portfolio_state`・`database_state`・`runtime_state` schemaへ保存する。

専用ロール `syncnesto_tfstate` は管理権限・継承・RLS bypassを持たない。state DBへのCONNECT/CREATEとstate schemaの操作だけを許可する。PUBLICのDB接続とschema権限を剥奪し、アプリロールからの接続を拒否する。stateロールもアプリDBへ接続できない。Neon direct接続と `sslmode=verify-full` を使用し、PostgreSQL advisory lockで同時操作を防ぐ。

backendが共通state IDのsequenceを `public` schemaに作るため、この専用DB内だけでstateロールに `public` のUSAGE/CREATEを許可する。アプリDBの権限は拡張しない。

資格情報はGitHub `production` Environmentの `TF_STATE_DATABASE_URL` と、Git管理外の `.env.terraform-state.local` に保存する。Vercelには登録しない。backend設定には `schema_name` だけを記載し、接続URIは `PG_CONN_STR` で渡す。

3構成の既存local stateは移行前に `state-backups/` へ所有者専用の権限で保存した。移行時にresources・outputsの一致を確認する。pg backendではlineage・serialが再作成されるため、復旧時には古いバックアップを無条件でpushしない。

`scripts/bootstrap_shared_state.py` は初回構築・移行用。既にpg backendへ移行した構成は非空stateを確認してスキップする。state DBは、それ自身を管理するTerraformの外でbootstrapする。Neonプロジェクトの `prevent_destroy` を維持する。プロジェクトごと失うとstateも失うため、`state-backups/` を安全な場所へバックアップする。

## Actionsの動き

`.github/workflows/terraform.yml` はPRでTerraformのformat・validate・mockテストとPythonのlint・compileを実行する。この段階ではクラウドのSecretsとstateを使用しない。

`main` へのpush後は本番のplanを実行する。applyはGitHubのActions画面で **Terraform validation and production apply → Run workflow → Branch: main → operation: apply** を選ぶ。CLIでは以下。

```bash
gh workflow run terraform.yml --repo shima-hei/syncnesto-infra --ref main -f operation=apply
```

共有stateを取得した後、project → database → runtimeの順でplan・applyする。空のstateからの実行と、削除を含むplanは拒否する。GitHub concurrencyとDB lockを併用し、実行中のapplyを新しいrunでキャンセルしない。生のTerraformログやstate・planをActions artifactへアップロードしない。ログには変更数・resource address・actionだけを表示する。

適用する公開設定は `terraform/portfolio/production.tfvars.example`。CIでは `production.auto.tfvars` としてコピーする。接続先・region等を変更する場合はこのファイルをPRでレビューする。Vercelの環境変数変更後は、FE/BEのデプロイworkflowを再実行して反映する。

`production` EnvironmentのSecretsは設定済み。

- `TF_STATE_DATABASE_URL`
- `VERCEL_API_TOKEN`
- `NEON_API_KEY`
- `SUPABASE_S3_ACCESS_KEY_ID`
- `SUPABASE_S3_SECRET_ACCESS_KEY`

Environmentは `main` からだけ使用できる。S3キー更新時はruntimeの `credential_version` も増やす。

## ローカル実行

既存のMakeコマンドは専用state資格情報ファイルを読み、共有stateを使用する。

```bash
zsh -ic 'make portfolio-plan'
zsh -ic 'make database-plan'
zsh -ic 'make runtime-plan'
zsh -ic 'python3 scripts/run_portfolio_ci.py plan'
zsh -ic 'uv run --project ../syncnesto-backend python scripts/verify_shared_state.py'
```

インフラapplyではアプリmigrationやseedは実行しない。migrationはバックエンドのActionsが担当し、初期seedは従来の専用スクリプトで行う。

[Terraform pg backendとロック](https://developer.hashicorp.com/terraform/language/backend/pg)
