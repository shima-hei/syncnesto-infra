.DEFAULT_GOAL := help
PYTHON ?= uv run python
DEPLOY = $(PYTHON) -m scripts.deploy
TF = terraform -chdir=terraform/localstack

.PHONY: help check
.PHONY: localstack-up localstack-down terraform-init terraform-validate terraform-plan terraform-apply terraform-destroy s3-ls sqs-list
.PHONY: vercel-init vercel-validate vercel-test vercel-plan vercel-apply db-migrate
.PHONY: neon-init neon-validate neon-test neon-plan neon-apply
.PHONY: runtime-init runtime-validate runtime-test runtime-plan runtime-apply
.PHONY: deploy-plan deploy-apply verify-database verify-state verify-web storage-verify

help:
	@printf '%s\n' 'Local: localstack-up / localstack-down / terraform-{init,validate,plan,apply}' 'Vercel: vercel-{init,validate,test,plan,apply}' 'Neon: neon-{init,validate,test,plan,apply}' 'Runtime: runtime-{init,validate,test,plan,apply}' 'All production stacks: deploy-plan / deploy-apply' 'Verification: check / verify-database / verify-state / verify-web / storage-verify' 'Application migrations: db-migrate'

# ローカル開発
localstack-up:
	docker compose up -d

localstack-down:
	docker compose down

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
	uv run ruff check scripts tests
	uv run ruff format --check scripts tests
	uv run python -m unittest discover -s tests -v
	terraform -chdir=terraform fmt -check -recursive
	$(DEPLOY) validate
