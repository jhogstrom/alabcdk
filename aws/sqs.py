from .utils import (gen_name, get_params)
from aws_cdk import (
    core as cdk,
    aws_sqs)


class Queue(aws_sqs.Queue):
    def __init__(
            self,
            scope: cdk.Construct,
            id: str,
            **kwargs):
        """
        Creates a Queue

        defaults:
        - queue_name - defaults to gen_name(scope, id) if not set.
        """
        kwargs.setdefault('queue_name', gen_name(scope, id))

        super().__init__(scope, id, **kwargs)