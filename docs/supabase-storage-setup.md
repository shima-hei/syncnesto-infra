# Supabase Storageの接続設定

確認済みのプロジェクトは `syncnesto`（`pdyywnoregglnyjlapta`）、地域はSingapore
（`ap-southeast-1`）。管理用の `SUPABASE_ACCESS_TOKEN` と、S3用のアクセスキーは別の資格情報です。
現在の管理トークンはプロジェクトを参照できますが、組織情報は403となるためFreeプランは未確認です。

## Dashboardで行うこと

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
設定後は「Freeを確認し、S3キーを設定した」と伝えれば次の工程を進められます。

## 次に適用する設定

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

S3キー設定後に非公開バケット `syncnesto-portfolio` とデフォルト画像を用意します。
現在のバケット一覧は空で、バケット作成・実アップロードの検証はまだ行っていません。
署名付きPUT/GET、匿名取得の拒否、ブラウザのCORS preflight、アプリのアップロード完了処理を実環境で確認してから公開します。

SupabaseのS3 APIは `PutBucketCors`・`PutBucketLifecycleConfiguration` に対応していません。
AWS向けのCORS/lifecycle設定をそのまま適用せず、プラットフォームのCORS応答を検証し、
`pending-uploads/` の1日以上古いファイルをS3 APIで清掃する運用を別途用意します。
RLSを迂回するS3キーは全バケットにアクセスできるため、このプロジェクトはデモ専用で使います。
ブラウザへ渡すのは権限検証後の短期署名付きURLだけです。

Freeのファイル容量は1GB、無操作1週間でプロジェクトが停止します。

## 公式資料

- [S3の認証とキーの管理](https://supabase.com/docs/guides/storage/s3/authentication)
- [S3 APIの対応範囲](https://supabase.com/docs/guides/storage/s3/compatibility)
- [Freeプランの条件](https://supabase.com/pricing)
