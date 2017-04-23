import logging
import os
import json
import boto3

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logging.getLogger('boto3').setLevel(logging.CRITICAL)
logging.getLogger('botocore').setLevel(logging.CRITICAL)

def lambda_handler(event, context):
    logger.info(json.dumps(event, indent=4))
    # boto3 goes here to spawn codebuild job
