.PHONY: bootstrap init prepare plan apply guardrail-env

guardrail-env:
	@. ./bin/tf-env.sh 2>/dev/null || true; \
	eval "$$(./bin/load-guardrail-ssm.sh $$(terraform workspace show 2>/dev/null || echo dev))"; \
	echo "GUARDRAIL_ID=$$GUARDRAIL_ID"; \
	echo "GUARDRAIL_VERSION=$$GUARDRAIL_VERSION"

.PHONY: bootstrap init prepare plan apply

bootstrap:
	./bin/bootstrap.sh

init:
	./bin/init-backend.sh

prepare:
	@chmod +x bin/*.sh
	@mkdir -p .build
	./bin/build-agent-zip.sh ../.. $(CURDIR)/.build/agent-runtime.zip
	./bin/build-telegram-lambda.sh ../lambdas/telegram_webhook $(CURDIR)/.build/telegram_webhook.zip

plan: prepare init
	@. ./bin/tf-env.sh && \
	terraform workspace select dev 2>/dev/null || terraform workspace new dev; \
	terraform plan -var-file=dev.tfvars -input=false

apply: prepare init
	@. ./bin/tf-env.sh && \
	terraform workspace select dev 2>/dev/null || terraform workspace new dev; \
	terraform apply -var-file=dev.tfvars -input=false -auto-approve
