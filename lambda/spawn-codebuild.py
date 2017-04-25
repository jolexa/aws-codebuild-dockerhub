import logging
import os
import json
import uuid
import shutil
import datetime
from posixpath import basename
import boto3

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logging.getLogger('boto3').setLevel(logging.CRITICAL)
logging.getLogger('botocore').setLevel(logging.CRITICAL)

try:
    region = os.environ['AWS_DEFAULT_REGION']
except:
    region = 'us-east-2'

def create_dummy_s3_input():
    client = boto3.client('s3')
    bucketname = "aws-codebuild-dockerhub-{}-{}".format(
            boto3.client('sts').get_caller_identity().get('Account'),
            str(uuid.uuid4().get_hex().lower()[0:10])
            )
    # create bucket
    response = client.create_bucket(
        Bucket=bucketname,
        CreateBucketConfiguration={
            'LocationConstraint': region
        }
    )
    # create zip
    shutil.make_archive("/tmp/dummyzipfile", 'zip')
    # Upload zip
    upload = client.put_object(
        Body=open("/tmp/dummyzipfile.zip", 'r'),
        Bucket=bucketname,
        Key="dummyzipfile.zip"
        )
    os.remove("/tmp/dummyzipfile.zip")

    return bucketname, "dummyzipfile.zip"

def lambda_handler(event, context):
    logger.info(json.dumps(event, indent=4))

    repo_url = event.get('repo_url')
    repo_path = basename(repo_url).split('.git')[0]
    username = event.get('username')

    client = boto3.client('codebuild')

    for build_target in event.get('builds'):

        bucketname, obj = create_dummy_s3_input()

        buildjob = client.create_project(
            name='-'.join([
                'aws-codebuild-dockerhub',
                build_target,
                str(uuid.uuid4().get_hex().lower()[0:10])
                ]),
            source={
                'type': 'S3',
                'location': "{}/{}".format(bucketname, obj),
                'buildspec': '''
version: 0.1
phases:
  build:
    commands:
      - git clone {0}
      - cd {1}/{2} && [ -e Dockerfile ] && curl -sL
        https://github.com/Versent/unicreds/releases/download/v1.5.0/unicreds_1.5.0_linux_x86_64.tgz
        | tar zx && docker build -t {3}/{2} . && docker login -u {3} -p
        $(./unicreds -r {4} get {5}) && docker push {3}/{2} && docker logout
  post_build:
    commands:
      - aws s3 rb s3://{6} --force
      '''.format(
          repo_url,     # 0 https://github.com/username/repo.git
          repo_path,    # 1 repo
          build_target, # 2 directory in repo
          username,     # 3 username
          region,
          os.getenv('CredstashLeadingKey'),
          bucketname
          ),
            },
            artifacts={
                'type': 'NO_ARTIFACTS',
            },
            environment={
                'type': 'LINUX_CONTAINER',
                'image': 'aws/codebuild/docker:1.12.1',
                'computeType': 'BUILD_GENERAL1_SMALL',
            },
            serviceRole=os.getenv('CodeBuildRoleArn'),
            timeoutInMinutes=5,
            tags=[
                {
                    "key": "X-Created-S3-Bucket",
                    "value": bucketname
                },
                {
                    "key": "X-Created-Date",
                    "value": str(datetime.date.today())
                },
                {
                    "key": "X-Delete-Via-Lambda-Eligible",
                    "value": "True"
                }
            ]
        )
        # Start the build
        startbuild = client.start_build(
            projectName=buildjob['project']['name']
        )

if __name__ == '__main__':
    event = {}
    context = {}
    lambda_handler(event, context)
