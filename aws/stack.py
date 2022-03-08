from .utils import (gen_name, get_params)
from constructs import Construct
from aws_cdk import (
    Stack)

class AlabStack(Stack):
    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            *,
            stage: str = None,
            user: str = None,
            **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.stage = stage
        self.user = user
