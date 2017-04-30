import logging
import os
import hmac
from hashlib import sha1
import json
import re

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
    # some sanity checking, only support ping and push
    if event['headers']['X-GitHub-Event'] == "ping":
        logger.info("ping event, returning")
        return {
            'body': "pong",
            'statusCode': 200
            }
    elif event['headers']['X-GitHub-Event'] != "push":
        logger.critical("hook event is not supported")
        return {
            'body': "hook event is not supported",
            'statusCode': 501
            }

    if githookbody['repository']['private']: # bool
        logger.info("Event Accepted but Private Repos are not supported")
        return {
            'body': "Event Accepted but Private Repos are not supported",
            'statusCode': 200
            }

    repo_url = githookbody['repository']['url'] + ".git"
    username = githookbody['repository']['owner']['name']
    builds_list = []

    # https://developer.github.com/v3/activity/events/types/#pushevent
    # Check the commits array for added or modified files, if the path contains
    # a "/" it probably fits the opionated repo structure
    for i in githookbody['commits']:
        for a in i['added']:
            if re.search("/", a):
                builds_list.append(a.split("/")[0])
        for m in i['modified']:
            if re.search("/", m):
                builds_list.append(m.split("/")[0])
    # Removes dupes to prevent spawning duplicate jobs
    builds = list(set(builds_list))

    # Spawn the CodeBuild Job
    if builds: # False if empty
        import boto3
        client = boto3.client('lambda')
        message_input = {
            'repo_url': repo_url,
            'builds': builds,
            'username': username,
            }
        logger.debug(message_input)
        response = client.invoke(
            FunctionName=os.environ['SpawnCodeBuildFunctionArn'],
            InvocationType='Event', # async
            LogType='None',
            Payload=json.dumps(message_input)
        )
    else:
        logger.info("Not spawning a codebuild job due to input/commit")

    # Everything is good
    return {
        "statusCode": 200,
        "body": "accepted"
    }
