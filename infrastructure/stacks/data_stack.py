"""
infrastructure/stacks/data_stack.py
DynamoDB ProdeTable + 4 GSIs + Streams + Cognito User Pool
TASK: TASK-INFRA-002 / TASK-INFRA-003 | ADR: ADR-003
"""
import aws_cdk as cdk
import aws_cdk.aws_dynamodb as dynamodb
import aws_cdk.aws_cognito  as cognito
from constructs import Construct
from infrastructure.db.dynamodb_tables import ProdeTableConstruct


class DataStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, env_name: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        self.env_name = env_name

        table_construct   = ProdeTableConstruct(self, "ProdeTable", env_name=env_name)
        self.table        = table_construct.table
        self.user_pool    = self._create_user_pool()

    def _create_user_pool(self) -> cognito.UserPool:
        user_pool = cognito.UserPool(
            self, "ProdeUserPool",
            user_pool_name   = f"ProdeUserPool-{self.env_name}",
            self_sign_up_enabled = True,
            sign_in_aliases  = cognito.SignInAliases(username=True),
            custom_attributes = {
                "platform":     cognito.StringAttribute(mutable=True),
                "platform_id":  cognito.StringAttribute(mutable=False),  # SHA-256 hash
                "display_name": cognito.StringAttribute(mutable=True),
            },
            password_policy = cognito.PasswordPolicy(
                min_length=8, require_digits=False,
                require_lowercase=False, require_symbols=False, require_uppercase=False,
            ),
            removal_policy = cdk.RemovalPolicy.RETAIN if self.env_name == "prod"
                             else cdk.RemovalPolicy.DESTROY,
        )
        user_pool.add_client(
            "ProdeAppClient",
            generate_secret      = False,
            auth_flows           = cognito.AuthFlow(user_password=True, user_srp=True),
            access_token_validity  = cdk.Duration.hours(24),
            refresh_token_validity = cdk.Duration.days(30),
        )
        return user_pool
