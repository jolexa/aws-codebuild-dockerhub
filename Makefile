ACCOUNT=$(shell aws sts get-caller-identity --query Account --output text)
# These variables need to be changed
STACKNAME="aws-codebuild-dockerhub"
KeyIdArn=$(shell aws kms --region us-east-2 describe-key --key-id arn:aws:kms:us-east-2:$(ACCOUNT):alias/credstash --query KeyMetadata.Arn --output text)
PRIMARY_REGION="us-east-2"
# Must be in PRIMARY_REGION, for artifacts
BUCKET="aws-codebuild-dockerhub"
GHSECRET="qwerty"
WebhookEndpoint="foo.example.tld"
WebhookEndpointZoneName="example.tld."

# Probably not used for average deploy, only for web
STANDBY_REGION="us-west-2"

deploy: upload customdomain
	aws cloudformation deploy \
        --template-file cfn-deployment.yml \
        --stack-name $(STACKNAME)-infra \
        --region $(PRIMARY_REGION) \
        --parameter-overrides \
        "DeploymentBucket=$(BUCKET)" \
		"md5=$(shell md5sum lambda/*.py| md5sum | cut -d ' ' -f 1)" \
		"KeyIdArn=$(KeyIdArn)" \
		"CloudFrontDistro=$(shell custom-domain-infra/scripts/get_domain_name_distro.py --domain-name $(WebhookEndpoint) --region $(PRIMARY_REGION))" \
		"WebhookEndpoint=$(WebhookEndpoint)" \
		"WebhookEndpointZoneName=$(WebhookEndpointZoneName)" \
		"GHSECRET=$(GHSECRET)" \
        --capabilities CAPABILITY_IAM || exit 0

upload:
	cd lambda && zip -r9 deployment.zip *.py && \
		aws s3 cp ./deployment.zip \
		s3://$(BUCKET)/$(shell md5sum lambda/*.py| md5sum | cut -d ' ' -f 1) && \
		rm -f deployment.zip

acm-cert:
	# Only works in us-east-1
	aws cloudformation deploy \
        --template-file custom-domain-infra/acm_certs.yml \
        --stack-name $(STACKNAME)-acm-certs \
        --region us-east-1 \
        --parameter-overrides "ACMUrl=$(WebhookEndpoint)" \
        --capabilities CAPABILITY_IAM || exit 0


customdomain: acm-cert
	# This script is not idempotent, will exit 1 if ran twice
	custom-domain-infra/scripts/create_domain_name.py \
		--cert-arn $(shell aws cloudformation --region us-east-1 describe-stacks --stack-name $(STACKNAME)-acm-certs --query Stacks[0].Outputs[0].OutputValue --output text) \
		--domain-name $(WebhookEndpoint) --region $(PRIMARY_REGION) || exit 0

website-infra:
	cd website-infra && \
		make STACKNAME_BASE=aws-codebuild-dockerhub-website \
		PRIMARY_REGION=$(PRIMARY_REGION) \
		STANDBY_REGION=$(STANDBY_REGION) \
		PRIMARY_URL=aws-codebuild-dockerhub.jolexa.us \
		STANDBY_URL=aws-codebuild-dockerhub-standby.jolexa.us

push-html-primary-bucket:
	aws s3 sync --sse --acl public-read html/ \
		s3://$(shell website-infra/scripts/find-cfn-output-value.py --region $(PRIMARY_REGION) --output-key PrimaryS3BucketName --stack-name aws-codebuild-dockerhub-website-primary-infra)/
	website-infra/scripts/invalidate-all.py aws-codebuild-dockerhub.jolexa.us
