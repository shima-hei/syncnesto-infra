.DEFAULT_GOAL := help
PYTHON ?= uv run python
DEPLOY = $(PYTHON) -m scripts.deploy
TF = terraform -chdir=terraform/localstack

.PHONY: help check
.PHONY: shared-files-up shared-files-init shared-files-stop
SHARED_FILES_ENV_FILE ?= $(HOME)/.local/share/syncnesto/storage/shared-files.env
SHARED_FILES_COMPOSE = docker compose --project-name syncnesto-shared-files --env-file "$(SHARED_FILES_ENV_FILE)" -f docker-compose.shared-files.yml

shared-files-up:
	$(SHARED_FILES_COMPOSE) up -d

shared-files-init:
	$(PYTHON) -m scripts.shared_file_delivery --env-file "$(SHARED_FILES_ENV_FILE)" init

.PHONY: verification-evidence-init
verification-evidence-init:
	$(PYTHON) -m scripts.verification_evidence_storage --env-file "$(SHARED_FILES_ENV_FILE)"

shared-files-stop:
	$(SHARED_FILES_COMPOSE) stop shared-files
.PHONY: localstack-up localstack-down terraform-init terraform-validate terraform-plan terraform-apply terraform-destroy s3-ls sqs-list
.PHONY: mailpit-up mailpit-stop
.PHONY: vercel-init vercel-validate vercel-test vercel-plan vercel-apply db-migrate
.PHONY: neon-init neon-validate neon-test neon-plan neon-apply
.PHONY: runtime-init runtime-validate runtime-test runtime-plan runtime-apply
.PHONY: deploy-plan deploy-apply verify-database verify-state verify-web storage-verify

help:
	@printf '%s\n' 'Local: localstack-up / localstack-down / mailpit-up / mailpit-stop / terraform-{init,validate,plan,apply}' 'Vercel: vercel-{init,validate,test,plan,apply}' 'Neon: neon-{init,validate,test,plan,apply}' 'Runtime: runtime-{init,validate,test,plan,apply}' 'All production stacks: deploy-plan / deploy-apply' 'Verification: check / verify-database / verify-state / verify-web / storage-verify' 'Application migrations: db-migrate'

# ローカル開発
localstack-up:
	docker compose up -d

localstack-down:
	docker compose down

mailpit-up:
	docker compose up -d --no-deps mailpit

mailpit-stop:
	docker compose stop mailpit

terraform-init terraform-validate terraform-plan terraform-apply terraform-destroy:
	$(TF) $(patsubst terraform-%,%,$@)

s3-ls:
	AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=ap-northeast-1 aws --endpoint-url=http://localhost:4566 s3 ls

sqs-list:
	AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=ap-northeast-1 aws --endpoint-url=http://localhost:4566 sqs list-queues

# 公開環境
vercel-init vercel-validate vercel-test vercel-plan vercel-apply:
	$(DEPLOY) terraform $(patsubst vercel-%,%,$@)

neon-init neon-validate neon-test neon-plan neon-apply:
	$(DEPLOY) terraform neon $(patsubst neon-%,%,$@)

runtime-init runtime-validate runtime-test runtime-plan runtime-apply:
	$(DEPLOY) terraform runtime $(patsubst runtime-%,%,$@)

deploy-plan deploy-apply:
	$(DEPLOY) ci $(patsubst deploy-%,%,$@)

db-migrate:
	$(DEPLOY) migrate

verify-database verify-state verify-web:
	$(DEPLOY) $@

storage-verify:
	$(DEPLOY) storage verify

# クラウド資格情報を使わない検証
check:
	uv run python -m scripts.verify
