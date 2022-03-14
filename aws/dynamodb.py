from typing import Sequence
from .utils import (gen_name, get_params, remove_params, stage_based_removal_policy, generate_output)
from constructs import Construct
from aws_cdk import (
    aws_iam,
    aws_lambda,
    aws_dynamodb)
class Table(aws_dynamodb.Table):
    """
    Creates a DynamoDB table with CDK.

    URL:
    - https://docs.aws.amazon.com/cdk/api/latest/docs/aws-dynamodb-readme.html
    - https://docs.aws.amazon.com/cdk/api/latest/python/aws_cdk.aws_dynamodb/Table.html

    Parameters (extra and those with changed behaviour):
    - table_name (str): gen_name(scope, id) if not set
    """
    def grant_access(self, *, grantees, grantfunc, env_var_name) -> None:
        for grantee in grantees:
            grantfunc(grantee)
            if isinstance(grantee, aws_lambda.Function):
                grantee.add_environment(env_var_name, self.table_name)

    def __init__(
            self,
            scope: Construct,
            id: str,
            *,
            partition_key=aws_dynamodb.Attribute(
                name='id',
                type=aws_dynamodb.AttributeType.STRING
            ),
            point_in_time_recovery=True,
            readers: Sequence[aws_iam.IGrantable] = None,
            writers: Sequence[aws_iam.IGrantable] = None,
            readers_writers: Sequence[aws_iam.IGrantable] = None,
            env_var_name: str = None,
            **kwargs):
        kwargs = get_params(locals())

        kwargs.setdefault('table_name', gen_name(scope, id))
        kwargs.setdefault("removal_policy", stage_based_removal_policy(scope))
        remove_params(kwargs, ["env_var_name", "readers", "writers", "readers_writers"])
        # kwargs.pop("env_var_name")
        # kwargs.pop("readers")
        # kwargs.pop("writers")
        # kwargs.pop("readers_writers")

        super().__init__(scope, id, **kwargs)
        env_var_name = env_var_name or id
        generate_output(self, env_var_name, self.table_name)
        self.grant_access(
            grantees=readers or [],
            grantfunc=self.grant_read_data,
            env_var_name=env_var_name)
        self.grant_access(
            grantees=writers or [],
            grantfunc=self.grant_write_data,
            env_var_name=env_var_name)
        self.grant_access(
            grantees=readers_writers or [],
            grantfunc=self.grant_read_write_data,
            env_var_name=env_var_name)
