#!/usr/bin/env python3

# AWS ip-ranges.json updater for Route Tables and/or Security Groups
# By Michael Ludvig

import os
import sys
import re
import json
import boto3
from botocore.exceptions import ClientError
from httplib2 import Http

ip_ranges_url = "https://ip-ranges.amazonaws.com/ip-ranges.json"

ec2 = boto3.resource('ec2')

def fatal(message):
    print("ERROR: %s" % message, file=sys.stderr)
    sys.exit(1)

def select_prefixes(ip_ranges_url, select):
    try:
        resp, content = Http().request(ip_ranges_url)
        if resp.status != 200:
            fatal("Unable to load %s - %d %s" % (ip_ranges_url, resp.status, resp.reason))
        content = content.decode('latin1')
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
                        _pfx.append(prefix)
            elif op == '-':
                # Exclude this service
                for prefix in prefixes:
                    if prefix['rgn'] == region and service not in prefix['svc']:
                        _pfx.append(prefix)
            else:
                # Include this service
                for prefix in prefixes:
                    if prefix['rgn'] == region and service in prefix['svc']:
                        _pfx.append(prefix)
    prefixes = _pfx

    return prefixes

def update_routes(route_table_id, prefixes, target):
    route_table = ec2.RouteTable(route_table_id)
    target_kwargs = {}
    if target.startswith('nat-'):
        target_kwargs['NatGatewayId'] = target
    elif target.startswith('igw-'):
        target_kwargs['GatewayId'] = target
    elif target.startswith('eni-'):
        target_kwargs['NetworkInterfaceId'] = target
    elif target.startswith('i-'):
        target_kwargs['InstanceId'] = target
    else:
        fatal("Unsupported route target: %s" % target)

    for prefix in prefixes:
        try:
            route_table.create_route(
                DestinationCidrBlock=prefix['net'],
                **target_kwargs,
            )
            print("ADDED: %s %s %s" % (route_table_id, target, prefix['net']))
        except ClientError as e:
            if e.response['Error']['Code'] != 'RouteAlreadyExists':
                raise

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
        print('Environment variable $SELECT must be set and be in a valid JSON format.', file=sys.stderr)
        raise

    route_table_ids = os.environ.get('ROUTE_TABLES')
    rt_target = os.environ.get('RT_TARGET')
    security_group_ids = os.environ.get('SECURITY_GROUPS')
    sg_ingress_ports = os.environ.get('SG_INGRESS_PORTS')
    sg_egress_ports = os.environ.get('SG_EGRESS_PORTS')

    if not route_table_ids and not security_group_ids:
        fatal('Environment variables $ROUTE_TABLES and/or $SECURITY_GROUPS must be set.')

    if route_table_ids and not rt_target:
        fatal('Environment variable $RT_TARGET must be set along with $ROUTE_TABLES')

    if security_group_ids and not sg_ingress_ports and not sg_egress_ports:
        fatal('Environment variables $SG_INGRESS_PORTS and/or $SG_EGRESS_PORTS must be set along with $SECURITY_GROUPS')

    # Split and normalise the inputs
    route_table_ids = split_and_check(route_table_ids, 'rtb-[0-9a-z]+', 'Invalid $ROUTE_TABLES member format, must be rtb-abcd1234')
    rt_target = rt_target.strip()
    security_group_ids = split_and_check(security_group_ids, 'sg-[0-9a-z]+', 'Invalid $SECURITY_GROUPS member format, must be sg-abcd1234')
    sg_ingress_ports = split_and_check(sg_ingress_ports, '[a-z]+/[0-9]+', 'Invalid $SG_INGRESS_PORTS member format, must be tcp/1234 or udp/1234')
    sg_egress_ports = split_and_check(sg_egress_ports, '[a-z]+/[0-9]+', 'Invalid $SG_EGRESS_PORTS member format, must be tcp/1234 or udp/1234')

    prefixes = select_prefixes(ip_ranges_url, select)
    print("SELECTED: %d prefixes" % len(prefixes))
    for rt_id in route_table_ids:
        update_routes(rt_id, prefixes, rt_target)

    for sg_id in security_group_ids:
        update_secgroup(sg_id, prefixes, sg_ingress_ports, sg_egress_ports)

if __name__ == "__main__":
    lambda_handler({}, {})
