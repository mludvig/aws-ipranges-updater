#!/usr/bin/env python3

# AWS ip-ranges.json updater for Route Tables and/or Security Groups
# By Michael Ludvig

import os
import sys
import re
import json
import socket
from http.client import HTTPSConnection
from urllib.parse import urlparse

import boto3                                    # pylint: disable=import-error
from botocore.exceptions import ClientError     # pylint: disable=import-error

ip_ranges_url = "https://ip-ranges.amazonaws.com/ip-ranges.json"
parsed_url = urlparse(ip_ranges_url)

ec2 = boto3.resource('ec2')
ec2_client = boto3.client('ec2')    # Needed for replace_route() :(

def fatal(message):
    print("ERROR: %s" % message, file=sys.stderr)
    sys.exit(1)

def select_prefixes(select):
    try:
        conn = HTTPSConnection(parsed_url.netloc)
        conn.connect()
        conn.request(method='GET', url=parsed_url.path)
        resp = conn.getresponse()
        if resp.status != 200:
            fatal("Unable to load %s - %d %s" % (ip_ranges_url, resp.status, resp.reason))
        content = resp.read()
        ipranges = json.loads(content)
    except Exception as e:
        fatal("Unable to load %s - %s" % (ip_ranges_url, e))

    if 'prefixes' not in ipranges or not ipranges['prefixes']:
        fatal("No prefixes found")

    pfx_dict = {}
    for prefix in ipranges['prefixes']:
        ip_prefix = prefix['ip_prefix']
        if ip_prefix not in pfx_dict:
            pfx_dict[ip_prefix] = {}
            pfx_dict[ip_prefix]['net'] = ip_prefix
            pfx_dict[ip_prefix]['rgn'] = prefix['region']
            pfx_dict[ip_prefix]['svc'] = [ prefix['service'] ]
        else:
            pfx_dict[ip_prefix]['svc'].append(prefix['service'])

    # Full prefix list
    prefixes = list(pfx_dict.values())

    _pfx = []
    services_exclude = []
    for select_one in select:
        region = select_one['region']
        services = select_one['services']

        for service in services:
            # Examine the service's first character to see the operand (+, -, =)
            if service[0] in '+-=':
                op = service[0]
                service = service[1:]
            else:
                # if none is specified assume '+'
                op = '+'

            if op == '=':
                # Select records that have ONLY this service
                for prefix in prefixes:
                    if prefix['rgn'] == region and service in prefix['svc'] and len(prefix['svc']) == 1:
                        if not _pfx.count(prefix):
                            _pfx.append(prefix)
            elif op == '-':
                # Process exclusions later
                services_exclude.append({'region': region, 'service': service})
            else:
                # Include this service
                for prefix in prefixes:
                    if prefix['rgn'] == region and service in prefix['svc']:
                        if not _pfx.count(prefix):
                            _pfx.append(prefix)

    prefixes = _pfx
    _pfx = []
    for exclude in services_exclude:
        region = exclude['region']
        service = exclude['service']
        for prefix in prefixes:
            if prefix['rgn'] == region and service not in prefix['svc']:
                if not _pfx.count(prefix):
                    _pfx.append(prefix)

    prefixes = _pfx
    # Order the prefixes
    prefixes = sorted(prefixes, key = lambda x: socket.inet_aton(x['net'].split('/')[0]))

    return prefixes

def update_routes(route_table_id, prefixes, target):
    if target.startswith('nat-'):
        arg_name = 'NatGatewayId'
    elif target.startswith('igw-'):
        arg_name = 'GatewayId'
    elif target.startswith('eni-'):
        arg_name = 'NetworkInterfaceId'
    elif target.startswith('i-'):
        arg_name = 'InstanceId'
    else:
        fatal("Unsupported route target: %s" % target)

    route_table = ec2.RouteTable(route_table_id)
    target_kwargs = { arg_name: target }
    for prefix in prefixes:
        existing_route = [route for route in route_table.routes_attribute if route.get('DestinationCidrBlock') == prefix['net']]
        if existing_route:
            if existing_route[0][arg_name] == target:
                continue    # The same route already exists
            else:
                ec2_client.replace_route(
                    RouteTableId=route_table_id,
                    DestinationCidrBlock=prefix['net'],
                    **target_kwargs,
                )
                print("REPLACED: %s %s %s was: %r" % (route_table_id, target, prefix['net'], existing_route[0]))
        else:
            ec2_client.create_route(
                RouteTableId=route_table_id,
                DestinationCidrBlock=prefix['net'],
                **target_kwargs,
            )
            print("ADDED: %s %s %s" % (route_table_id, target, prefix['net']))

def update_secgroup(security_group_id, prefixes, sg_ingress_ports, sg_egress_ports):
    def _insert_rule(label, func, portspec, prefix):
        proto, port = portspec.split('/')
        try:
            func(IpPermissions=[{
                'IpRanges': [{'CidrIp': prefix['net']}],
                'FromPort': int(port),
                'ToPort': int(port),
                'IpProtocol': proto
            }])
            print("ADDED: %s %s %s" % (label, portspec, prefix['net']))
        except ClientError as e:
            if e.response['Error']['Code'] != 'InvalidPermission.Duplicate':
                raise

    security_group = ec2.SecurityGroup(security_group_id)

    for prefix in prefixes:
        for port_spec in sg_ingress_ports:
            _insert_rule("%s/in" % security_group_id, security_group.authorize_ingress, port_spec, prefix)
        for port_spec in sg_egress_ports:
            _insert_rule("%s/out" % security_group_id, security_group.authorize_egress, port_spec, prefix)


def split_and_check(param, pattern, helptext):
    '''
    Split the supplied 'param' by commas, strip whitespaces and check against regexp pattern.
    '''
    if not param:
        return []
    params = [ x.strip() for x in param.split(',') ]
    for p in params:
        if not re.match(pattern, p):
            fatal(helptext)
    return params

def lambda_handler(event, context):
    try:
        select_str = os.environ['SELECT']
        select = json.loads(select_str)
        # Try to access the minimum required attributes
        # to trigger exception if the SELECT is invalid
        _ = select[0]["region"] + select[0]["services"][0]
    except:
        print('Environment variable $SELECT must be set and be in a valid JSON format.\n', file=sys.stderr)
        raise

    route_tables = os.environ.get('ROUTE_TABLES')
    rt_target = os.environ.get('RT_TARGET')
    security_groups = os.environ.get('SECURITY_GROUPS')
    sg_ingress_ports = os.environ.get('SG_INGRESS_PORTS')
    sg_egress_ports = os.environ.get('SG_EGRESS_PORTS')
    test_only = os.environ.get('TEST_ONLY') in [ '1', 'yes', 'true' ]

    if not route_tables and not security_groups:
        print('Environment variables $ROUTE_TABLES and/or $SECURITY_GROUPS should be set. Running in TEST_ONLY=yes mode.', file=sys.stderr)
        test_only = True

    if route_tables and not rt_target:
        fatal('Environment variable $RT_TARGET must be set along with $ROUTE_TABLES')

    if security_groups and not sg_ingress_ports and not sg_egress_ports:
        fatal('Environment variables $SG_INGRESS_PORTS and/or $SG_EGRESS_PORTS must be set along with $SECURITY_GROUPS')

    # Split and normalise the inputs
    route_tables = split_and_check(route_tables, 'rtb-[0-9a-z]+', 'Invalid $ROUTE_TABLES member format, must be rtb-abcd1234')
    rt_target = split_and_check(rt_target, '[a-z]+-', 'Invalid $RT_TARGET, must be a NAT ID, IGW ID, VGW ID, EC2 instance ID, etc')
    security_groups = split_and_check(security_groups, 'sg-[0-9a-z]+', 'Invalid $SECURITY_GROUPS member format, must be sg-abcd1234')
    sg_ingress_ports = split_and_check(sg_ingress_ports, '[a-z]+/[0-9]+', 'Invalid $SG_INGRESS_PORTS member format, must be tcp/1234 or udp/1234')
    sg_egress_ports = split_and_check(sg_egress_ports, '[a-z]+/[0-9]+', 'Invalid $SG_EGRESS_PORTS member format, must be tcp/1234 or udp/1234')

    if len(rt_target) > 1:
        fatal('Environment variable $RT_TARGET must have only one target, not a list')

    prefixes = select_prefixes(select)
    print("SELECTED: %d prefixes" % len(prefixes))

    if test_only:
        for prefix in prefixes:
            svcs = " ".join(prefix['svc'])
            print("{net:20}   {rgn:20}   {svcs}".format(**prefix, svcs=svcs))
    else:
        for rt_id in route_tables:
            update_routes(rt_id, prefixes, rt_target[0])

        for sg_id in security_groups:
            update_secgroup(sg_id, prefixes, sg_ingress_ports, sg_egress_ports)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description = "Test ip-ranges.json $SELECT statement")
    parser.add_argument("--json", required=True, help="JSON used for Lambda's SELECT statement. Must be in form [{\"region\":\"...\",\"services\":[\"...\",\"...\"]}]")
    args = parser.parse_args()
    os.environ['SELECT'] = args.json
    lambda_handler({}, {})
