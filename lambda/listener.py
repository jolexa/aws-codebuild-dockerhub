import logging
import os
import hmac
from hashlib import sha1
import json
import re
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
    # some sanity checking, only support pushes
    if event['headers']['X-GitHub-Event'] != "push":
        logger.critical("hook event is not supported")
        return {
            'body': "hook event is not supported",
            'statusCode': 501
            }

    repo_url = githookbody['repository']['url'] + ".git"
    username = githookbody['repository']['owner']['name']
    builds_list = []
    for i in githookbody['commits']:
        for a in i['added']:
            if re.search("/", a):
                builds_list.append(a.split("/")[0])
        for m in i['modified']:
            if re.search("/", m):
                builds_list.append(m.split("/")[0])
    # This is slow but don't care for our list size
    # Removes dupes to prevent spawning duplicate jobs
    builds = sorted(set(builds_list),key=builds_list.index)

    # Spawn the CodeBuild Job
    lambdac = boto3.client('lambda')
    message_input = {
        'repo_url': repo_url,
        'builds': builds,
        'username': username,
        }
    print message_input
    if builds: # False if empty
        response = lambdac.invoke(
            FunctionName=os.environ['SpawnCodeBuildFunctionArn'],
            InvocationType='Event', # async
            LogType='None',
            Payload=json.dumps(message_input)
        )
    else:
        logger.info("Not spawning a codebuild job")

    # Everything is good
    return {
        "statusCode": 200,
        "body": "worked"
    }
