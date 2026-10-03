# syncnesto-infra

LocalStackでの開発環境と、Vercel・Neonでのポートフォリオ公開環境を管理します。

GitHub Actionsによる検証・本番applyと、Neon上の共有stateについては [運用手順](docs/github-actions.md) を参照してください。

- `terraform/`: 既存のLocalStack用S3・SQS。
- `terraform/portfolio/`: Vercelプロジェクト・Neon DB。別のProvider・stateで管理します。

公開環境の設定と実行手順は [ポートフォリオ用Terraform](terraform/portfolio/README.md) を参照してください。

## LocalStackによる開発環境

この構成ではLocalStackの認証トークンを `.env` から読み込みます。2026年3月以降のLocalStack最新イメージは認証トークンが必要です。

## 前提

- Docker / Docker Compose
- Terraform
- AWS CLI

AWS本体には接続しません。Terraform ProviderはLocalStackのエンドポイント `http://localhost:4566` を参照します。

macOSでTerraformが未インストールの場合:

```bash
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```

## LocalStack認証トークン設定

`.env.example` をコピーして、取得したトークンを `.env` に設定します。

```bash
cp .env.example .env
```

`.env`:

```env
LOCALSTACK_AUTH_TOKEN=取得したトークン
```

`.env` はGit管理対象外です。トークンを `docker-compose.yml` やTerraformファイルへ直接書かないでください。

## LocalStack起動

```bash
docker compose up -d
```

起動確認:

```bash
docker compose ps
```

Makeを使う場合:

```bash
make localstack-up
```

起動時には `localstack/init/ready.d/10-bootstrap-resources.sh` が実行され、
S3バケット、バケットのversioning、SQSキュー、デフォルトアバターを冪等に作成します。
そのため、LocalStackのコンテナ再起動後もアプリに必要な初期リソースは自動的に復旧します。

現在使用しているfreemiumライセンスではLocalStackのスナップショット永続化を利用できません。
ユーザーがアップロードしたS3オブジェクトやSQSメッセージはコンテナ再起動をまたいで保存されないため、
永続化が必要なデータには別途バックアップまたは永続ストレージを用意してください。

## Terraform適用

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

Makeを使う場合:

```bash
make terraform-init
make terraform-plan
make terraform-apply
```

## 動作確認

AWS CLIではLocalStack向けのダミー認証情報を使います。

```bash
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=ap-northeast-1
```

S3:

```bash
aws --endpoint-url=http://localhost:4566 s3 ls
aws --endpoint-url=http://localhost:4566 s3 cp README.md s3://syncnesto-local-app-bucket/README.md
aws --endpoint-url=http://localhost:4566 s3 ls s3://syncnesto-local-app-bucket/
```

SQS:

```bash
QUEUE_URL=$(aws --endpoint-url=http://localhost:4566 sqs get-queue-url \
  --queue-name syncnesto-local-app-queue \
  --query QueueUrl \
  --output text)

aws --endpoint-url=http://localhost:4566 sqs send-message \
  --queue-url "$QUEUE_URL" \
  --message-body '{"event":"hello-localstack"}'

aws --endpoint-url=http://localhost:4566 sqs receive-message \
  --queue-url "$QUEUE_URL"
```

## バックエンドからS3へアクセス

LocalStackへ接続するバックエンドでは、本物のAWSではなくLocalStackのendpointを明示します。

必要な環境変数:

```bash
export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=ap-northeast-1
export S3_BUCKET_NAME=syncnesto-local-app-bucket
```

Boto3の最小例:

```python
import boto3

s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:4566",
    region_name="ap-northeast-1",
    aws_access_key_id="test",
    aws_secret_access_key="test",
)

s3.upload_file(
    "sample.png",
    "syncnesto-local-app-bucket",
    "images/sample.png",
    ExtraArgs={"ContentType": "image/png"},
)
```

このリポジトリには動作確認用のサンプルも置いています。

```bash
cd examples/python
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python upload_image.py /path/to/image.png
```

アップロード確認:

```bash
aws --endpoint-url=http://localhost:4566 s3 ls s3://syncnesto-local-app-bucket/images/
```

## 後片付け

Terraformリソース削除:

```bash
cd terraform
terraform destroy
```

LocalStack停止:

```bash
docker compose down
```
