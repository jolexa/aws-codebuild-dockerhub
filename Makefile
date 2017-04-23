BUCKET="aws-codebuild-dockerhub"
STACKNAME="aws-codebuild-dockerhub"

deploy: upload
	aws cloudformation deploy \
        --template-file apigw-lambda-deployment.yml \
        --stack-name $(STACKNAME)-infra \
        --region us-east-2 \
        --parameter-overrides \
        "DeploymentBucket=$(BUCKET)" \
		"md5=$(shell md5sum lambda/main.py | cut -d ' ' -f 1)" \
        --capabilities CAPABILITY_IAM || exit 0

upload:
	cd lambda && zip -r9 deployment.zip main.py && \
		aws s3 cp ./deployment.zip \
		s3://$(BUCKET)/$(shell md5sum lambda/main.py | cut -d ' ' -f 1) && \
		rm -f deployment.zip
