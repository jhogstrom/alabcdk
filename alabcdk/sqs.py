from typing import Sequence
from .utils import (gen_name)
from constructs import Construct
from aws_cdk import (
    aws_iam,
    aws_lambda,
    aws_sqs)


class Queue(aws_sqs.Queue):
    def grant_access(self, *, grantees, grantfunc, env_var_name) -> None:
        for grantee in grantees:
            grantfunc(grantee)
            if isinstance(grantee, aws_lambda.Function):
                grantee.add_environment(env_var_name, self.table_name)

    def __init__(
            self,
            scope: Construct,
            id: str,
            senders: Sequence[aws_iam.IGrantable] = None,
            consumers: Sequence[aws_iam.IGrantable] = None,
            env_var_name: str = None,
            **kwargs):
        """
        Creates a Queue

        defaults:
        - queue_name - defaults to gen_name(scope, id) if not set.
        """
        kwargs.setdefault('queue_name', gen_name(scope, id))

        super().__init__(scope, id, **kwargs)

        self.grant_access(
            grantees=senders or [],
            grantfunc=self.grant_send_messages,
            env_var_name=env_var_name)
        self.grant_access(
            grantees=consumers or [],
            grantfunc=self.grant_consume_messages,
            env_var_name=env_var_name)
