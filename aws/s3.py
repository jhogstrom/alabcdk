from .utils import (gen_name, get_params)
from constructs import Construct
from aws_cdk import (
    aws_s3)


class Bucket(aws_s3.Bucket):
    def __init__(
            self,
            scope: Construct,
            id: str,
            *,
            block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
            **kwargs):
        """
        Creates an S3 bucket, using some sensible defaults for security.

        See https://docs.aws.amazon.com/cdk/api/latest/python/aws_cdk.aws_s3/Bucket.html
        for a detailed description of parameters.

        - :param bucket_name: defaults to gen_name(scope, id) if not set
        """
        kwargs = get_params(locals())

        # Set the name to a standard
        kwargs.setdefault("bucket_name", gen_name(scope, id).lower().replace("_", "-"))

        super().__init__(scope, id, **kwargs)