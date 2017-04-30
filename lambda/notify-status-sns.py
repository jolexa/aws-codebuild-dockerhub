import logging
import os
import time
import json
import boto3

logging.basicConfig()
logging.getLogger('boto3').setLevel(logging.CRITICAL)
logging.getLogger('botocore').setLevel(logging.CRITICAL)
logger = logging.getLogger("mylogger")
logger.setLevel("DEBUG")

try:
    region = os.environ['AWS_DEFAULT_REGION']
except:
    region = 'us-east-2'

def lambda_handler(event, context):
    logger.info(json.dumps(event, indent=4))
    client = boto3.client('codebuild', region_name=region)
    snsclient = boto3.client('sns', region_name=region)
    # build_id passed in the event
    build_id = event.get('build_id')
    build_name = build_id.split(":")[0]

    response = client.batch_get_builds(ids=[build_id])
    logger.debug(response)

    # There will only be one item in the response
    build_status = response['builds'][0]['buildStatus']
    logs_link = response['builds'][0]['logs']['deepLink']
    # The lambda will be invoked before the CoeBuild job is actually finished.
    # It seems like, about 4 seconds prior to finishing
    while build_status == "IN_PROGRESS":
        response = client.batch_get_builds(ids=[build_id])
        build_status = response['builds'][0]['buildStatus']
        time.sleep(5)

    # Send a success/failure subject with link to the logs
    if build_status != "SUCCEEDED":
        logger.info("Something went wrong in the builds, sending notification")
        snsclient.publish(
            TopicArn=os.getenv('NotifyFunctionSNSArn'),
            Subject="CodeBuild Failed: {}".format(build_name),
            Message='For more details, goto {}'.format(logs_link),
            )
    else:
        logger.info("Build Succeeded, sending notification")
        snsclient.publish(
            TopicArn=os.getenv('NotifyFunctionSNSArn'),
            Subject="CodeBuild Suceeded: {}".format(build_name),
            Message='For more details, goto {}'.format(logs_link),
            )
