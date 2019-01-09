ip-ranges RouteTable / SecurityGroup updater
============================================

Lambda function that updates the list of CIDRs in a given AWS Route Table
or Security Group with prefixes obtained from the official AWS address register:
https://ip-ranges.amazonaws.com/ip-ranges.json

Lambda is called periodically 1x per day. That's enough becuase `ip-ranges.json`
doesn't change that often.

Configuration
-------------

Configuration parameters are read from `config.sh` (use `config.sh.template`
to start with).

To select certain prefixes from ip-ranges.json use the following
JSON syntax:

```
SELECT = [
	{
		"region": "ap-southeast-2",
		"services": [ "+AMAZON", "+EC2", "-S3" ]
    },
	{
		"region": "us-east-1",
		"services": [ "=AMAZON" ]
	}
]
```

The above filter will select prefixes from `ap-southeast-2` that
have either `AMAZON` or `EC2` service but _not_ `S3` service.
From `us-east-1` only the prefixes that have only `AMAZON` service
tag and no other tags (e.g. will not select a prefix that is _both_
`AMAZON` and `EC2`).

To update a _Route Table_ pass in these two variables:

* ROUTE_TABLES = rtb-12345678, rtb-abcdefgh
* RT_TARGET = igw-..., nat-..., vgw-...

To update a _Security Group_ pass in these variables:

* SECURITY_GROUPS = sg-1234abcd, sg-abcd1234
* SG_INGRESS_PORTS = tcp/80, tcp/443
* SG_EGRESS_PORTS = tcp/443, udp/1234

JSON Filter testing
-------------------

The lambda source file can be run from the shell to facilitate the JSON
filter testing.

```
$ ./ipranges_updater/lambda.py --json '[{"region":"ap-southeast-2","services":["S3"]}]'
Environment variables $ROUTE_TABLES and/or $SECURITY_GROUPS should be set. Running in TEST_ONLY=yes mode.
SELECTED: 4 prefixes
52.92.52.0/22          ap-southeast-2         AMAZON S3
52.95.128.0/21         ap-southeast-2         AMAZON S3
54.231.248.0/22        ap-southeast-2         AMAZON S3
54.231.252.0/24        ap-southeast-2         AMAZON S3
```

Deployment
----------

The `deploy.sh` script and the _CloudFormation_ `template.yaml` use
_AWS SAM_ (Serverless Application Model) and `aws cloudformation deploy` command.

To use the provided deploy script first copy `config.sh.template`
to `config.sh` and fill in your settings. Comment out parameters
that you don't need!

Then run `./deploy.sh` and wait.

After a while you will see **ipranges-updater** stack deployed in the region of your choice.

Permissions
-----------

The lambda function needs permissions to update the _Security Groups_ and/or
the _Route Tables_.

Author
------

Michael Ludvig @ Enterprise IT Ltd

For more info visit https://aws.nz/projects/ipranges-updater/
