from typing import Sequence, List
from .utils import (gen_name, generate_output)
from constructs import Construct
from aws_cdk import (
    aws_sns,
    aws_sns_subscriptions,
    aws_iam,
    aws_lambda)
import aws_cdk as cdk


class Topic(aws_sns.Topic):
    def update_environment(self, env_var_name: str, receivers: List):
        for receiver in receivers:
            if isinstance(receiver, aws_lambda.Function):
                receiver.add_environment(env_var_name, self.topic_arn)

    def __init__(
            self,
            scope: Construct,
            id: str,
            *,
            env_var_name: str = None,
            subscribers: Sequence[aws_lambda.Function] = None,
            publishers: Sequence[aws_iam.IGrantable] = None,
            **kwargs):
        """
        Creates a Topic and optionally adds lambda subscribers.

        defaults:
        - topic_name - defaults to gen_name(scope, id) if not set.
        """
        kwargs.setdefault('topic_name', gen_name(scope, id))
        subscribers = subscribers or []
        publishers = publishers or []

        super().__init__(scope, id, **kwargs)
        env_var_name = env_var_name or id
        for fn in subscribers:
            self.add_subscription(aws_sns_subscriptions.LambdaSubscription(fn))
        for grantee in publishers:
            self.grant_publish(grantee)

        self.update_environment(env_var_name, subscribers)
        self.update_environment(env_var_name, publishers)
        generate_output(self, env_var_name, self.topic_arn)
