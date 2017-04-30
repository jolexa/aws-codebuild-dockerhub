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
benefits of #serverless builds and automatic updating in the future, if I made a
change or commit. Even if I had **one** repo full of _Dockerfiles_, like [Jess
Frazelle](https://github.com/jessfraz/dockerfiles), it would still be too much
configuring for a non-automated solution to configure autobuilds.

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
[`credstash`](https://github.com/fugue/credstash) for the `<owner>`

(Aside, I found it comical that AWS suggests to
[**not**](https://docs.aws.amazon.com/codebuild/latest/userguide/build-env-ref.html)
put passwords in CodeBuild environment variables, then shows an
[example](https://docs.aws.amazon.com/codebuild/latest/userguide/sample-docker.html#sample-docker-docker-hub)
doing just that. (shrug) )

After the CodeBuild job is completed, the
[SNS Notifier function](https://github.com/jolexa/aws-codebuild-dockerhub/blob/master/lambda/notify-status-sns.py)
is invoked. The
[AWS Sample shows](https://docs.aws.amazon.com/codebuild/latest/userguide/sample-build-notifications.html)
an awscli command to publish to SNS, but I desired richer content than the
example.

Once per week a CodeBuild cleanup lambda is executed that removes jobs older
than a week. This is a compromise that I decided to implement because the
CodeBuild job will not be ran again (therefore not cost anything), but I may
want to see why it failed in lieu of automatically cleaning up right away.

![Architecture Diagram](https://raw.githubusercontent.com/jolexa/aws-codebuild-dockerhub/master/diagram.png)

## How?
If you want to deploy this for yourself. Clone the repo, modify the top
lines of the
[Makefile](https://github.com/jolexa/aws-codebuild-dockerhub/blob/master/Makefile#L1-L7)
and run `make` - this will deploy multiple cloudformation stacks.  Described
below:

1. Stack to provision one ACM cert (must be us-east-1)
  * If you want a custom domain for the API Gateway (nicety only)
2. Infrastructure stack (any region that support CodeBuild)
  * API Gateway
  * Listener Lambda
  * CodeBuild Spawner Lambda
  * SNS Notifier Lambda and SNS Topic
    * Optionally subscribe to topic, reports success/failures
  * Cleanup Lambda (runs once per week)

There are additional helpers in the Makefile to provision this
[website](https://aws-codebuild-dockerhub.jolexa.us/)

#### Advanced How to Use
For the advanced user, you will want to:
1. Change the GitHub Secret that is used
2. Modify the API GW custom domain.
3. Many modifications if you choose not to use credstash
  * credstash must be in the same region as `PRIMARY_REGION`

Something like this:
```
make customdomain WebhookEndpoint="example.jolexa.us"

make WebhookEndpoint=example.jolexa.us WebhookEndpointZoneName=jolexa.us GHSECRET=mysecret
```

* After deploying the infrastructure, add a webhook to your GitHub repo that
   sends a json payload to the endpoint

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
  to configure autobuilds programatically.

## Cost

In practice, this architecture is pretty cheap, for _me_. I don't commit many updates to my [Dockerfiles repo](https://github.com/jolexa/dockerfiles)

* API Gateway: Fractions of penny per commit or request.
* CodeBuild: The most expensive thing, as described above. Variable cost @ $0.005/min
* Lambdas: Fractions of penny per commit and fraction of penny per week (for cleanup function)
* SNS: Fraction of a penny for commit.
* credstash: KMS and Dynamodb table will cost something (if you don't use credstash otherwise).

Most of these pennies will be within the perpetual free tier as well so the
actual cost will vary depending on your account size, and commit frequency.

## Questions / Contact
I will be more than happy to answer any questions on GitHub Issues and review
Pull Requests to make this reference even better. Feel free to reach me on
[Twitter](https://twitter.com/jolexa) as well.
