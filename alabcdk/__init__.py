
from typing import Sequence
from constructs import Construct
from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    aws_events,
    aws_apigateway,
    aws_lambda,
    aws_s3,
    aws_events_targets,
    aws_cloudfront,
    aws_cloudfront_origins,
    aws_certificatemanager)

from .utils import (gen_name, get_params, filter_kwargs, generate_output)
from .lambdas import Function, PipLayers  # noqa401
from .dynamodb import Table  # noqa401
from .sqs import Queue  # noqa401
from .s3 import Bucket  # noqa401
from .sns import Topic  # noqa401
from .cloudfront import Website  # noqa401
from .stack import AlabStack  # noqa401
from .ssm import StringParameter  # noqa401
from .redshift import RedshiftServerless, RedshiftCluster # noqa401
from .billing import BillingAlert # noqa401
from .backup import BackupPlan # noqa401
from .data_ingestion_api import DataIngestionApi

class Rule(aws_events.Rule):
    def __init__(
            self,
            scope: Construct,
            id: str,
            target: aws_lambda.Function = None,
            **kwargs):
        kwargs = get_params(locals())
        if all([target, kwargs.get("targets")]):
            raise Exception("You may only specify one of 'target' and 'targets")

        if target:
            kwargs.setdefault("targets", [aws_events_targets.LambdaFunction(target)])
        kwargs.setdefault("rule_name", gen_name(scope, id))
        super().__init__(scope, id, **kwargs)


class RestApi(aws_apigateway.RestApi):
    def __init__(
            self,
            scope: Construct,
            id: str,
            **kwargs):
        """
        Creates a RestApi with some sensible defaults.

        defaults:
        - rest_api_name -> gen_name(scope, id) if not set
        """
        kwargs.setdefault('rest_api_name', gen_name(scope, id))

        # Set default deploy options
        kwargs.setdefault('deploy_options', aws_apigateway.StageOptions(
            logging_level=aws_apigateway.MethodLoggingLevel.INFO,
            metrics_enabled=True))

        super().__init__(scope, id, **kwargs)

        generate_output(self, id, self.url)


class ResourceWithLambda(Construct):
    '''
    Construct that wraps the creation of a lambda function,
    optionally a resource and adds a method to the resource
    integrated with the lambda.
    '''
    def __init__(
            self,
            scope: Construct,
            id: str, *,
            parent_resource: aws_apigateway.IResource,
            code: aws_lambda.Code = None,
            description: str = None,
            verb: str = "ANY",
            resource_name: str = None,
            integration_request_templates: dict = {"application/json": '{ "statusCode": "200" }'},
            resource_add_child: bool = True,
            **kwargs):
        '''
        Create a lambda function and hook it up to a resource
        with a lambda integration.

        To standardize code, the following defaults are used:

        * function.handler => "{id}.main"

        * function.function_name => "{self.gen_name(f'{id}_handler')}"

        * If resource_name is not set the method will be named {id}

        To simplify passing additional arguments to the sub-parts, any argument
        prefixed with:

        lambda_ -> will be send to the Function constructor

        method_ -> will be sent to add_method()

        integration_ -> will be sent to the integration constructor
        '''
        super().__init__(scope, f"{id}_ResourceWithLambda")
        kwargs = get_params(locals())

        if resource_name and not resource_add_child:
            self.node.add_error(f"{type(self).__name__}('{id}'): Cannot specify both resource_add_child=True and set a resource_name ('{resource_name}').")  # noqa e501

        if not resource_name:
            resource_name = id

        lambda_kwargs = filter_kwargs(kwargs, "lambda_")
        method_kwargs = filter_kwargs(kwargs, "method_")
        integration_kwargs = filter_kwargs(kwargs, "integration_")

        lambda_kwargs.setdefault("function_name", gen_name(scope, f"{id}"))
        lambda_kwargs.setdefault("handler", f"{id}.main")
        if code:
            lambda_kwargs['code'] = code

        # TODO: Wrap this in a canarydeploy. That may be a breaking change unfortunately.
        handler = Function(
            scope,
            f"{id}",
            description=description,
            **lambda_kwargs
        )
        self.handler = handler

        self.integration = aws_apigateway.LambdaIntegration(self.handler, **integration_kwargs)

        if resource_add_child:
            self.resource = parent_resource.add_resource(resource_name)
        else:
            self.resource = parent_resource
        self.method = self.resource.add_method(verb, self.integration, **method_kwargs)
        CfnOutput(
            self,
            f"{id}_url",
            value=f"{id}:: {self.resource.url} -- {verb}",
            description=f"url for {id}")


class WebsiteXX(Construct):
    def __init__(
            self,
            scope: Construct,
            id: str,
            *,
            index_document: str = None,
            error_document: str = None,
            cors_rules: Sequence[aws_s3.CorsRule] = None,
            domain_names: Sequence[str] = None,
            certificate: aws_certificatemanager.Certificate = None,
            certificate_arn: str = None,
            backend: aws_apigateway.IRestApi = None,
            **kwargs) -> None:
        """Create a bucket and a CDN in front of it. The CDN will be connected to a
        certificate and domain_names if provided. Passing a backend will also add
        the backend behind /api

        Args:
            scope (core.Construct): Scope of construct
            id (str): id of construct
            index_document (str, optional): Index document in the bucket. Defaults to "index.html" if not set.
            error_document (str, optional): Error document in bucket. Defaults to index_document.
            cors_rules (Sequence[aws_s3.CorsRule], optional): Cors rules for the bucket.
            Defaults to GET/*/* if not set.
            domain_names (Sequence[str], optional): Aliases for the CDN. Defaults to None.
            certificate (aws_certificatemanager.Certificate, optional): Certificate for the CDN.
            Defaults to None if certificate_arn is not set.
            certificate_arn (str, optional): [description]. arn to an existing certificate.
            backend (aws_apigateway.IRestApi, optional): Backend to include in the CDN. Defaults to None.

        Raises:
            ValueError: [description]
        """
        super().__init__(scope, f"{id}_website")

        if all([certificate, certificate_arn]):
            raise ValueError("You cannot pass values for both 'certificate' and 'certificate_arn'.")
        kwargs = get_params(locals())
        bucket_kwargs = filter_kwargs(kwargs, "bucket_")
        cdn_kwargs = filter_kwargs(kwargs, "cdn_")

        index_document = index_document or "index.html"
        error_document = error_document or "index.html"
        cors_rules = cors_rules or [aws_s3.CorsRule(
                allowed_methods=[aws_s3.HttpMethods.GET],
                allowed_headers=["*"],
                allowed_origins=["*"])]

        routing_rules = []
        error_responses = []
        for error_code in ["403", "404"]:
            routing_rules.append(
                aws_s3.RoutingRule(
                    condition=aws_s3.RoutingRuleCondition(
                        http_error_code_returned_equals=error_code,
                    ),
                    replace_key=aws_s3.ReplaceKey.prefix_with("#!")
                )
            )
            error_responses.append(aws_cloudfront.CfnDistribution.CustomErrorResponseProperty(
                        error_code=int(error_code),
                        response_page_path="/index.html",
                        response_code=200))

        self.bucket = Bucket(
            self,
            f"{id}_bucket",
            website_index_document=index_document,
            website_error_document=error_document,
            block_public_access=bucket_kwargs.pop("block_public_access", None) or None,
            public_read_access=True,
            website_routing_rules=routing_rules,
            cors=cors_rules,
            **bucket_kwargs)
        self.bucket.grant_public_access()
        CfnOutput(self, "S3WebUrl", value=self.bucket.bucket_website_url, )

        if not certificate and certificate_arn:
            certificate = aws_certificatemanager.Certificate.from_certificate_arn(
                self,
                f"{id}_certificate",
                certificate_arn
            )

        self.distribution = aws_cloudfront.Distribution(
            self,
            f"{id}_distro",
            comment=f"CDN for {id}",

            default_behavior=aws_cloudfront.BehaviorOptions(
                origin=aws_cloudfront_origins.S3Origin(self.bucket)
            ),
            price_class=aws_cloudfront.PriceClass.PRICE_CLASS_100,
            domain_names=domain_names,
            certificate=certificate,
            default_root_object=index_document,
            **cdn_kwargs
        )
        if backend:
            self.distribution.add_behavior(
                "/api/*",
                origin=aws_cloudfront_origins.HttpOrigin(
                    f"{backend.rest_api_id}.execute-api.{Stack.of(self).region}.amazonaws.com",
                    origin_path=f"/{backend.deployment_stage.stage_name}"
                ),
                allowed_methods=aws_cloudfront.AllowedMethods.ALLOW_ALL,
                cache_policy=aws_cloudfront.CachePolicy(
                    self,
                    f"{id}_api_cachepolicy",
                    cookie_behavior=aws_cloudfront.CacheCookieBehavior.all(),
                    query_string_behavior=aws_cloudfront.CacheQueryStringBehavior.all(),
                    default_ttl=Duration.seconds(0),
                    header_behavior=aws_cloudfront.CacheHeaderBehavior.allow_list("Authorization")
                )
            )

        CfnOutput(self, "CDNUrl", value=self.distribution.distribution_domain_name)
