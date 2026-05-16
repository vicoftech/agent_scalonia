"""tests/conftest.py"""
import os
os.environ.setdefault("AWS_DEFAULT_REGION",    "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID",     "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN",    "testing")
os.environ.setdefault("AWS_SESSION_TOKEN",     "testing")
os.environ.setdefault("DYNAMODB_TABLE",        "ProdeTable-test")
os.environ.setdefault("AGENTCORE_AGENT_ID",    "test-agent-id")
os.environ.setdefault("AGENTCORE_AGENT_ALIAS", "LIVE")
os.environ.setdefault("LOG_LEVEL",             "WARNING")
