import logging
import os
import hmac
from hashlib import sha1
import json
import boto3

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logging.getLogger('boto3').setLevel(logging.CRITICAL)
logging.getLogger('botocore').setLevel(logging.CRITICAL)

def lambda_handler(event, context):
    logger.info(json.dumps(event, indent=4))
    try:
        # Get the sha_name and sig from the headers
        sha_name, sig = event['headers']['X-Hub-Signature'].split('=')
        # Get the body of the message
        body = event['body']
        # Only support sha1
        if sha_name != 'sha1':
            return {
                "statusCode": 501,
                "body": "Something is wrong, unsupported sha type?\n"
            }
    except Exception as e:
        logger.exception(e)
        return {
            "statusCode": 501,
            "body": "Something is wrong, not from GitHub?\n"
        }

    secret = os.environ['GHSECRET']
    # HMAC requires the key to be bytes, but data is string
    mac = hmac.new(secret, body, sha1)
    if not hmac.compare_digest(unicode(mac.hexdigest()), unicode(sig)):
        logger.critical("Signature doesn't match")
        return {
            'body': "Signature doesn't match",
            'statusCode': 403
            }

    githookbody = json.loads(body)
    logger.debug(json.dumps(githookbody, indent=4))
    # some sanity checking
    if githookbody['hook']['events'][0] != "push":
        logger.critical("hook event is not supported")
        return {
            'body': "hook event is not supported",
            'statusCode': 501
            }

    # Everything is good
    return {
        "statusCode": 200,
        "body": "worked"
    }
