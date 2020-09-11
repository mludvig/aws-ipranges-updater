import os
import sys
import json
from pathlib import Path

import yaml

import pytest

sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "ipranges_updater")))

#from ipranges_updater.index import get_ipranges
import index

ipranges_location = "tests/ip-ranges.json"

class SelectTestCase:
    def __init__(self, test_case):
        self.select = test_case['select']
        self.expect = test_case['expect']

    def __repr__(self):
        return self.select

def load_test_cases(path):
    with open(path, "rt") as f:
        test_cases = yaml.safe_load_all(f)
        return [ SelectTestCase(test_case) for test_case in test_cases ]

def list_files(path):
    filelist = list(Path(".").glob(path))
    filelist.sort()
    # Turn into a list of strings for prettier output in pytest
    return [str(p) for p in filelist]

def load_yaml_file(select_file):
    with open(select_file, "rt") as f:
        return yaml.safe_load(f)

def find_prefixes(prefixes, wanted):
    return [pfx["net"] for pfx in filter(lambda x: x['net'] in wanted, prefixes)]

# === Tests follow ===

def test_get_ipranges_local():
    ipranges = index.get_ipranges(ipranges_location)
    assert "createDate" in ipranges

@pytest.mark.parametrize("test_case", load_test_cases("tests/select-test-cases.yaml"), ids=str)
def test_select_prefixes(test_case):
    ipranges = index.get_ipranges(ipranges_location)
    prefixes = index.select_prefixes(ipranges, json.loads(test_case.select))

    if "present" in test_case.expect:
        match = find_prefixes(prefixes, test_case.expect["present"])
        assert set(match) == set(test_case.expect["present"])
    if "not_present" in test_case.expect:
        match = find_prefixes(prefixes, test_case.expect["not_present"])
        assert not match    # match must be empty
    if "count" in test_case.expect:
        assert len(prefixes) == int(test_case.expect["count"])
