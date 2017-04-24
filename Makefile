BUCKET="aws-codebuild-dockerhub"
STACKNAME="aws-codebuild-dockerhub"
ACCOUNT=$(shell aws sts get-caller-identity --query Account --output text)
KeyIdArn=$(shell aws kms --region us-east-2 describe-key --key-id arn:aws:kms:us-east-2:$(ACCOUNT):alias/credstash --query KeyMetadata.Arn --output text)

deploy: upload
	aws cloudformation deploy \
        --template-file cfn-deployment.yml \
        --stack-name $(STACKNAME)-infra \
        --region us-east-2 \
        --parameter-overrides \
        "DeploymentBucket=$(BUCKET)" \
		"md5=$(shell md5sum lambda/*.py| md5sum | cut -d ' ' -f 1)" \
		"KeyIdArn=$(KeyIdArn)" \
        --capabilities CAPABILITY_IAM || exit 0

upload:
	cd lambda && zip -r9 deployment.zip *.py && \
		aws s3 cp ./deployment.zip \
		s3://$(BUCKET)/$(shell md5sum lambda/*.py| md5sum | cut -d ' ' -f 1) && \
		rm -f deployment.zip
