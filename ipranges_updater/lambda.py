#!/usr/bin/env python3

# AWS ip-ranges.json updater for Route Tables and/or Security Groups
# By Michael Ludvig

import os
import sys
import json
from httplib2 import Http

ip_ranges_url = "https://ip-ranges.amazonaws.com/ip-ranges.json"

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
    print("SELECTED: %d prefixes" % len(prefixes))

    return prefixes

def lambda_handler(event, context):
    try:
        select_str = os.environ['SELECT']
        select = json.loads(select_str)
        # Try to access the minimum required attributes
        # to trigger exception if the SELECT is invalid
        _ = select[0]["region"] + select[0]["services"][0]
    except:
        print('Environment variable SELECT must be set and be in a valid JSON format.', file=sys.stderr)
        raise

    prefixes = select_prefixes(ip_ranges_url, select)


if __name__ == "__main__":
    lambda_handler({}, {})
