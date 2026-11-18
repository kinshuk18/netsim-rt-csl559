"""
Test Suite for NetSim-RT Sandboxed Custom Policy Execution & Escape Attempts
CSL559 Computer Systems Design - IIT Bhilai
"""

import pytest
from engine.sandbox import validate_code_ast, run_sandboxed_simulation


def test_valid_custom_policy_ast():
    code = """
def select_next(queue, now, state):
    return 0
"""
    valid, err = validate_code_ast(code)
    assert valid is True
    assert err is None


def test_escape_attempt_import():
    code = """
import os
def select_next(queue, now, state):
    os.system("rm -rf /")
    return 0
"""
    valid, err = validate_code_ast(code)
    assert valid is False
    assert "Imports are strictly forbidden" in err


def test_escape_attempt_from_import():
    code = """
from subprocess import check_output
def select_next(queue, now, state):
    return 0
"""
    valid, err = validate_code_ast(code)
    assert valid is False
    assert "Imports are strictly forbidden" in err


def test_escape_attempt_dunder_attribute():
    code = """
def select_next(queue, now, state):
    # Try accessing subclass tree via dunder
    subclasses = ().__class__.__bases__[0].__subclasses__()
    return 0
"""
    valid, err = validate_code_ast(code)
    assert valid is False
    assert "Access to private attribute" in err


def test_escape_attempt_forbidden_builtins():
    code = """
def select_next(queue, now, state):
    open("/etc/passwd", "r")
    return 0
"""
    valid, err = validate_code_ast(code)
    assert valid is False
    assert "Calling builtin 'open' is forbidden" in err


def test_sandboxed_simulation_fallback_on_rejection():
    bad_code = """
import sys
def select_next(queue, now, state):
    return 0
"""
    cfg = {
        "trace_path": "data/processed/epa.parquet",
        "num_servers": 2,
        "max_requests": 50
    }
    res = run_sandboxed_simulation(bad_code, cfg, timeout_s=3.0)
    assert res["custom_policy_status"] == "rejected"
    assert res["fallback"] == "fcfs"
    assert "Security Violation" in res["custom_policy_error"]
