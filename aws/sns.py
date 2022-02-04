from typing import Sequence
from .utils import (gen_name, get_params)
from constructs import Construct
from aws_cdk import (
    aws_sns,
    aws_sns_subscriptions,
    aws_lambda)


class Topic(aws_sns.Topic):
    def __init__(
            self,
            scope: Construct,
            id: str,
            *,
            subscribers: Sequence[aws_lambda.Function] = None,
            **kwargs):
        """
        Creates a Topic and optionally adds lambda subscribers.

        defaults:
        - topic_name - defaults to gen_name(scope, id) if not set.
        """
        kwargs.setdefault('topic_name', gen_name(scope, id))
        subscribers = subscribers or []

        super().__init__(scope, id, **kwargs)
        for fn in subscribers:
            self.add_subscription(aws_sns_subscriptions.LambdaSubscription(fn))
