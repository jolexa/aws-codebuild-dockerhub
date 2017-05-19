import logging
import os
import json
import datetime
from dateutil import parser
import boto3
from botocore.exceptions import ClientError

logging.basicConfig()
logging.getLogger('boto3').setLevel(logging.CRITICAL)
logging.getLogger('botocore').setLevel(logging.CRITICAL)
logger = logging.getLogger("mylogger")
logger.setLevel("INFO")

try:
    region = os.environ['AWS_DEFAULT_REGION']
except:
    region = 'us-east-2'


def check_delete_candidate(codebuild):
    name = codebuild['name']
    logger.info("Checking: {}".format(name))
    tags = codebuild['tags']
    sevendaysago = datetime.datetime.now() - datetime.timedelta(days=7)
    for i in tags:
        key, value = i['key'], i['value']
        if key == "X-Delete-Via-Lambda-Eligible":
            if value == "True":
                logger.info("Delete via Lambda is True")
                for t in tags:
                    key, value = t['key'], t['value']
                    if key == 'X-Created-Date':
                        cdate = parser.parse(value)
                        if cdate < sevendaysago:
                            logger.info("Candidate for removal due to age")
                            return True
                        else:
                            logger.info("Created Date is not older than 7 days")
    logger.info("Not a candidate for removal")
    return False

def delete_s3_if_exists(codebuild):
    s3client = boto3.client('s3')
    for i in codebuild['tags']:
        key, bucketname = i['key'], i['value']
        if key == "X-Created-S3-Bucket":
            try:
                objs = s3client.list_objects_v2(
                        Bucket=bucketname
                        )
            except ClientError as e:
                if e.response['Error']['Code'] == 'NoSuchBucket':
                    logger.info("Bucket Already Deleted, not trying further")
                    return True
                else:
                    raise
            for i in objs['Contents']:
                logger.info("Deleting Object: {}".format(i))
                delete = s3client.delete_object(
                    Bucket=bucketname,
                    Key=i['Key']
                    )
            s3client.delete_bucket(Bucket=bucketname)
            logger.info("Deleted Bucket: {}".format(bucketname))
    return True

def lambda_handler(event, context):
    client = boto3.client('codebuild', region_name=region)

    logger.info(json.dumps(event, indent=4))

    # All this pagination code becuase boto3 doesn't support pagination on
    # coebuild at time of wrting
    projects_list = client.list_projects()
    projects = projects_list['projects']
    next_token = projects_list.get('nextToken')
    while next_token is not None:
        projects_list = client.list_projects(
            nextToken=next_token
            )
        projects.append(projects_list['projects'])
        next_token = projects_list.get('nextToken')
    # end pagination code, 'projects' is now ready to use

    for i in projects:
        response = client.batch_get_projects(names=[i])
        p = response['projects'][0] # there will only be one item in this list
        name = p['name']
        if check_delete_candidate(p):
            delete_s3_if_exists(p) # delete the orphaned s3 bucket
            client.delete_project(name=name)
            logger.info("Deleted project: {}".format(name))
            boto3.client('logs').delete_log_group(
                logGroupName='/aws/codebuild/' + name
            )

if __name__ == '__main__':
    # Running this from localhost with proper permissions will work as intended
    event = {}
    context = {}
    lambda_handler(event, context)
