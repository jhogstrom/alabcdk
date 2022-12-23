from aws_cdk import (
    aws_lambda as lambda_,
    aws_apigatewayv2_alpha as api_gw2,
    aws_apigatewayv2_authorizers_alpha as _authorizers,
    aws_apigatewayv2_integrations_alpha as _api_integrations
)
from constructs import Construct

class DataIngestionApi(Construct):
    def __init__(self, scope: Construct, construct_id: str, *,
                 name: str,
                 description: str) -> None:
        super().__init__(scope, construct_id)

        self._api = api_gw2.HttpApi(self, 'api',
                                    api_name=name,
                                    description=description)

    def add_stage(self, stage_name: str) -> None:
        self._api.add_stage(f'stage-{stage_name}', stage_name=stage_name)

    def add_ingestion_path_new_data(self, path: str,
                                    integration_fn: lambda_.IFunction,
                                    auth_name: str = 'authorizer',
                                    auth_handler: lambda_.IFunction = None) -> None:
        authorizer = api_gw2.HttpNoneAuthorizer
        if auth_handler is not None:
            authorizer = _authorizers.HttpLambdaAuthorizer(f'authorizer-{path}',
                                                           authorizer_name=auth_name,
                                                           handler=auth_handler,
                                                           identity_source=['$request.header.Authorization'],
                                                           response_types=[_authorizers.HttpLambdaResponseType.SIMPLE],
                                                           )
        integration = _api_integrations.HttpLambdaIntegration(f'integration-path', integration_fn)
        self._api.add_routes(path=path,
                             methods=[api_gw2.HttpMethod.POST],
                             authorizer=authorizer,
                             integration=integration)


