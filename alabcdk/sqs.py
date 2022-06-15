from .utils import (gen_name)
from constructs import Construct
from aws_cdk import (
    aws_sqs)


class Queue(aws_sqs.Queue):
    def __init__(
            self,
            scope: Construct,
            id: str,
            **kwargs):
        """
        Creates a Queue

        defaults:
        - queue_name - defaults to gen_name(scope, id) if not set.
        """
        kwargs.setdefault('queue_name', gen_name(scope, id))

        super().__init__(scope, id, **kwargs)
