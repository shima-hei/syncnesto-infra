.PHONY: localstack-up localstack-down terraform-init terraform-plan terraform-apply terraform-destroy s3-ls sqs-list
.PHONY: portfolio-init portfolio-validate portfolio-test portfolio-plan portfolio-apply
.PHONY: database-init database-validate database-plan database-apply

database-init:
	python3 scripts/portfolio_terraform.py database init

database-validate:
	python3 scripts/portfolio_terraform.py database validate

database-plan:
	python3 scripts/portfolio_terraform.py database plan

database-apply:
	python3 scripts/portfolio_terraform.py database apply

portfolio-init:
	python3 scripts/portfolio_terraform.py init

portfolio-validate:
	python3 scripts/portfolio_terraform.py validate

portfolio-test:
	python3 scripts/portfolio_terraform.py test

portfolio-plan:
	python3 scripts/portfolio_terraform.py plan

portfolio-apply:
	python3 scripts/portfolio_terraform.py apply

localstack-up:
	docker compose up -d

localstack-down:
	docker compose down

terraform-init:
	cd terraform && terraform init

terraform-plan:
	cd terraform && terraform plan

terraform-apply:
	cd terraform && terraform apply

terraform-destroy:
	cd terraform && terraform destroy

s3-ls:
	AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=ap-northeast-1 aws --endpoint-url=http://localhost:4566 s3 ls

sqs-list:
	AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=ap-northeast-1 aws --endpoint-url=http://localhost:4566 sqs list-queues
