"""infrastructure/app.py — CDK App. Deploy: cdk deploy --all --context env=staging"""
import aws_cdk as cdk
from stacks.data_stack import DataStack
# Sprint 0+: agregar AuroraStack, ApiStack, SchedulingStack, KBStack

app      = cdk.App()
env_name = app.node.try_get_context("env") or "staging"
env      = cdk.Environment(region="us-east-1")

DataStack(app, f"ProdeData-{env_name}", env=env, env_name=env_name)

app.synth()
