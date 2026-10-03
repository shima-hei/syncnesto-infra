# Supabase Storageの接続設定

確認済みのプロジェクトは `syncnesto`（`pdyywnoregglnyjlapta`）、地域はSingapore
（`ap-southeast-1`）。管理用の `SUPABASE_ACCESS_TOKEN` と、S3用のアクセスキーは別の資格情報です。
2026-10-04に利用者のBilling画面でFreeプラン・Spend cap有効・支払い方法未登録を確認しました。
管理APIの組織情報は403ですが、S3用キーの設定・実通信は確認済みです。

## キーの発行・更新手順

1. [組織のBilling画面](https://supabase.com/dashboard/org/yxsnqlgubcohdavdcpry/billing) を開き、現在のプランが **Free** であることを確認します。プラン変更は不要です。
2. [このプロジェクトのS3設定](https://supabase.com/dashboard/project/pdyywnoregglnyjlapta/storage/s3) を開きます。
3. **Access keys** 欄で新しいキーを作成し、名前を `syncnesto-vercel` にします。
4. 発行された **Access Key ID** と **Secret Access Key** をコピーします。
5. `~/.zshrc` の末尾に、以下の2行を追加して値を置き換えます。`export` は小文字です。

```bash
export SUPABASE_S3_ACCESS_KEY_ID='Access Key IDの値'
export SUPABASE_S3_SECRET_ACCESS_KEY='Secret Access Keyの値'
```

値をチャット、リポジトリ、フロントエンドの環境変数へ貼らないでください。
現在のキーは設定済みです。再発行時はruntime構成を再適用し、バックエンドを再デプロイしてから旧キーを失効させます。

## 適用済みの設定

`terraform/portfolio/runtime/` はVercelバックエンドのProductionに以下を登録します。

- `DATABASE_URL`: `syncnesto_app` の制限付きpooled URI。管理URIは渡しません。
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`: Supabase S3のキー。
- `AWS_S3_ENDPOINT_URL`: `https://pdyywnoregglnyjlapta.storage.supabase.co/storage/v1/s3`。
- `AWS_REGION=ap-southeast-1`、`AWS_S3_BUCKET_NAME=syncnesto-portfolio`。
- ダウンロード・アップロードURLの有効期間は600秒。

秘密の入力変数はephemeral、Vercelへの登録はwrite-onlyとし、このruntime state・planには値を保存しません。
資格情報更新時は `credential_version` を増やして再適用します。

```bash
make runtime-init
make runtime-validate
make runtime-test
zsh -ic 'make runtime-plan'
zsh -ic 'make runtime-apply'
```

## ストレージの準備と検証

非公開バケット `syncnesto-portfolio` を作成し、サイズ上限20MiBと `default-avatar.png` を設定しました。
署名付きPUT/GET、匿名・不正署名による取得の拒否、ブラウザのCORS preflight、アプリのアップロード完了処理を実環境で確認済みです。
runtime state・保存したplanにS3キーが含まれないことも検証しました。

以下はinfraルートから実行します。`prepare` は既存バケットの非公開設定・サイズ上限とデフォルト画像を更新するため、初期構築・復旧時に使用します。

```bash
zsh -ic 'uv run --project ../syncnesto-backend python scripts/portfolio_storage.py prepare'
zsh -ic 'uv run --project ../syncnesto-backend python scripts/portfolio_storage.py verify'
```

SupabaseのS3 APIは `PutBucketCors`・`PutBucketLifecycleConfiguration` に対応していません。
AWS向けのCORS/lifecycle設定をそのまま適用せず、プラットフォームのCORS応答を検証し、
`pending-uploads/` の1日以上古いファイルをS3 APIで清掃します。自動実行は設定していません。
まず対象件数を確認し、必要時に `--execute` を指定します。検証後の対象件数は0件でした。

```bash
zsh -ic 'uv run --project ../syncnesto-backend python scripts/portfolio_storage.py cleanup-pending'
zsh -ic 'uv run --project ../syncnesto-backend python scripts/portfolio_storage.py cleanup-pending --execute'
```

RLSを迂回するS3キーは全バケットにアクセスできるため、このプロジェクトはデモ専用で使います。
ブラウザへ渡すのは権限検証後の短期署名付きURLだけです。

Freeのファイル容量は1GB、無操作1週間でプロジェクトが停止します。

## 公式資料

- [S3の認証とキーの管理](https://supabase.com/docs/guides/storage/s3/authentication)
- [S3 APIの対応範囲](https://supabase.com/docs/guides/storage/s3/compatibility)
- [Freeプランの条件](https://supabase.com/pricing)
