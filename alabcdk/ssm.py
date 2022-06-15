
from typing import Sequence
from constructs import Construct
from aws_cdk import (
    aws_ssm,
    aws_iam,
)
import aws_cdk as cdk
from .utils import (gen_name, get_params, generate_output, remove_params)


class StringParameter(aws_ssm.StringParameter):
    def __init__(
            self,
            scope: Construct,
            id: str,
            *,
            readers: Sequence[aws_iam.IGrantable] = None,
            writers: Sequence[aws_iam.IGrantable] = None,
            readers_writers: Sequence[aws_iam.IGrantable] = None,
            removal_policy: cdk.RemovalPolicy = None,
            env_var_name: str = None,
            **kwargs):
        kwargs = get_params(locals())
        kwargs.setdefault('parameter_name', gen_name(scope, id))

        stack = cdk.Stack.of(scope)
        kwargs.setdefault('description', f"{stack.stack_name} parameter {id}")

        remove_params(kwargs, [
            "env_var_name",
            "readers",
            "writers",
            "readers_writers",
            "removal_policy"])
        super().__init__(scope, id, **kwargs)

        removal_policy = removal_policy or cdk.RemovalPolicy.DESTROY
        self.apply_removal_policy(removal_policy)

        env_var_name = env_var_name or id
        generate_output(self, env_var_name, self.parameter_name)

        readers = readers or []
        writers = writers or []
        readers_writers = readers_writers or []

        for reader in readers + readers_writers:
            self.grant_read(reader)
        for writer in writers + readers_writers:
            self.grant_write(writer)
