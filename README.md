https://aws-codebuild-dockerhub.jolexa.us/
===============
# aws-codebuild-dockerhub

## Motivation
In a nutshell, I was tired of configuring every single [Docker Hub automated
build](https://docs.docker.com/docker-hub/github/) myself and was looking for
some solution.

Until now, I had a GitHub repo _per_ tool/project to create a Docker image of
the said tool. This lead to **many** repos with one or a few file(s) in it, a
_Dockerfile_ and helpers, and not many commits after the initial creation. Yet,
I wanted to configure an autobuild on Docker Hub so that I could reap the
benefits of #serverless builds and automatic updating in the future if I made a
change or commit. Even if I had **one** repo full of _Dockerfiles_, like [Jess
Frazelle](https://github.com/jessfraz/dockerfiles), it would still be too much
configuring for a non-automated solution to configure autobuilds. (By the way,
this is the first place I look to see examples of how something works in Docker,
very appreciative!)

My goal is to provide a reference implementation of a Docker Hub build
replacement that has the following properties:
* minimal cost (or free)
* automated
* serverless
* easy to understand or modify

## What?
Spawn a Docker build automatically after a GitHub push event. The
architecture looks like below, built on [AWS CodeBuild
service](https://aws.amazon.com/codebuild/).

The [Listener function](https://github.com/jolexa/aws-codebuild-dockerhub/blob/master/lambda/listener.py)
is opinionated on the repo structure. The repo must consist of directories with
a `Dockerfile`. The Listener will
[**not**](https://github.com/jolexa/aws-codebuild-dockerhub/blob/master/lambda/listener.py#L53-L58)
spawn jobs for private repos, but you could implement this if desired. The
[Spawner function](https://github.com/jolexa/aws-codebuild-dockerhub/blob/master/lambda/spawn-codebuild.py)
will create a CodeBuild job for the commit, run
`docker build -t <owner>/<directory name> .`
then push it to Docker Hub with credentials provided by
[`EC2 SSM Parameter Store`](https://aws.amazon.com/ec2/systems-manager/parameter-store/) for the `<owner>`

After the CodeBuild job is completed, the
[SNS Notifier function](https://github.com/jolexa/aws-codebuild-dockerhub/blob/master/lambda/notify-status-sns.py)
is invoked. The
[AWS Sample shows](https://docs.aws.amazon.com/codebuild/latest/userguide/sample-build-notifications.html)
an awscli command to publish to SNS, but I desired richer content than the
example.

Once per week a CodeBuild cleanup lambda is executed that removes jobs older
than a week. This is a compromise that I decided to implement because the
CodeBuild job will not run again (therefore not cost anything), but I may
want to see why it failed in lieu of automatically cleaning up right away.

![Architecture Diagram](https://raw.githubusercontent.com/jolexa/aws-codebuild-dockerhub/master/diagram.png)

## How?
The
[Makefile](https://github.com/jolexa/aws-codebuild-dockerhub/blob/master/Makefile)
will deploy two cloudformation stacks and one helper command for the custom
domain.

1. [ACM certificate stack](https://github.com/jolexa/aws-apigw-acm/blob/master/acm_certs.yml) (must be `us-east-1`)
2. [Infrastructure stack](https://github.com/jolexa/aws-codebuild-dockerhub/blob/master/cfn-deployment.yml) (any region that supports CodeBuild)
  * API Gateway
    * BasePath Mapping for the custom domain endpoint
  * Listener Lambda
  * CodeBuild Spawner Lambda
  * SNS Notifier Lambda and SNS Topic
    * [Optional] Recommended to subscribe to topic as this reports success & failures.
  * Cleanup Lambda (runs once per week)

The deployment assumes the following things. There will need to be changes to
deviate from any these.
1. There is a hosted zone in Route53
2. Custom Domain is desired
3. Password saved in EC2 SSM Parameter Store is in the same region as the `PRIMARY_REGION`

There are additional helpers in the Makefile to provision this
[website](https://aws-codebuild-dockerhub.jolexa.us/)

* After deploying the infrastructure, add a webhook to your GitHub repo that
  sends a json payload to the endpoint. Enter the proper secret in the webhook
  config (this is scriptable but low return on invest since it is a one-time
  setup)

#### Theory
I choose to manage the API GW/Lambda/SNS infrastructure inside of CloudFormation
because it represents the most manageable methods available as well as the least
possible way of interfering with existing infrastructure. I chose to spawn
CodeBuild jobs with boto3 because it was a nice, quick way to create dynamic
jobs.

## Things I learned

* I was surprised that CodeBuild supports Docker-in-Docker, it is the core of
  this implementation.
* CodeBuild is surprisingly opinionated on the buildspec. It must be yaml and it
  is difficult to know what syntax is valid. I had a hard time invoking the
  notifier lambda.
* GitHub webhooks are flexible but marginally difficult to secure. SNS still
  might be better.
* GitHub infrastructure does **not** support IPv6 [webhooks]. I thought this
  would be a clever way to _hide_ my endpoint from bots (by obscurity).
* The `raw` feature of GitHub takes a few minutes to update.
* I still love **not** maintaining servers


### Shortcomings / Analysis
* CodeBuild is really expensive, $0.30/hour but billed per minute. You can get a
  `r4.xlarge` for that price on the on-demand market. So, it only makes sense to
  use CodeBuild if you are to be <15% utilized/active per hour. Check my math, a
  `t2.medium` is $0.047/hour, with similar specs as a `build.general1.small` if
  you run a CodeBuild job for 9 minutes it will cost $0.045 (9 minutes *
  0.005/min). The t2.medium will cost $0.047 for 9 minutes (since the minimum is
  one hour). 9 minutes of an hour is 15% of an hour. This math all breaks down
  on the spot market, and it might make sense to build-your-own pipeline for
  active projects.
  * (I hope I remain in the free tier, 100 minutes per month).
* Super opinionated reference but hopefully easy to modify for your use case.
  The Dockerfile path is opinionated, the Docker Hub account name is
  opinionated, etc.
* For Docker Hub, losing out of the GitHub integration features, like README or
  automatic linking.
* GitHub sends a maximum of 20 commits in a
  [PushEvent](https://developer.github.com/v3/activity/events/types/#pushevent)
  so some commits may get missed for large events
* Jobs only get spawned for git push, the code only handles master and doesn't
  attempt to checkout branches, though it could with some work since the
  ref/branch is sent in the event
* It is too difficult to find documentation for any of the Docker API's,
  apparently some exist and you may want to use a project like
  [RyanTheAllmighty/Docker-Hub-API](https://github.com/RyanTheAllmighty/Docker-Hub-API)
  to configure autobuilds programmatically.

## Cost

In practice, this architecture is pretty cheap, for _me_. I don't commit many updates to my [Dockerfiles repo](https://github.com/jolexa/dockerfiles)

* API Gateway: Fractions of a penny per commit or request.
* CodeBuild: The most expensive thing, as described above. Variable cost @ $0.005/min
* Lambdas: Fractions of a penny per commit and fraction of a penny per week (for cleanup function)
* SNS: Fraction of a penny for commit.
* KMS: Number of KMS decryptions will cost a fraction of penny

Most of these pennies will be within the perpetual free tier as well so the
actual cost will vary depending on your account size, and commit frequency.

## Questions / Contact
I will be more than happy to answer any questions on GitHub Issues and review
Pull Requests to make this reference even better. Feel free to reach me on
[Twitter](https://twitter.com/jolexa) as well.
