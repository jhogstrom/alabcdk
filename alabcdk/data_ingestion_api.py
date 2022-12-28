from typing import Optional
from aws_cdk import (
    Stack,
    aws_certificatemanager as acm,
    aws_lambda as lambda_,
    aws_route53 as route53,
    aws_route53_targets as route53_targets,
    aws_apigatewayv2_alpha as api_gw2,
    aws_apigatewayv2_authorizers_alpha as _authorizers,
    aws_apigatewayv2_integrations_alpha as _api_integrations
)
from constructs import Construct
from .utils import (gen_name, generate_output)


class ApiDomain(Construct):
    def __init__(self, scope: Construct, id: str, *,
                 domain_name: str,
                 zone_name: str,
                 hosted_zone_id: str,
                 certificate: Optional[acm.ICertificate] = None,
                 region: Optional[str] = None,
                 **kwargs) -> None:
        super().__init__(scope, id)

        self.name = domain_name
        self.hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
            self,
            gen_name(self, "hosted_zone"),
            hosted_zone_id=hosted_zone_id,
            zone_name=zone_name
        )

        self.certificate = certificate or acm.DnsValidatedCertificate(
            self,
            gen_name(self, "cert"),
            hosted_zone=self.hosted_zone,
            domain_name=domain_name,
            region=region or Stack.of(self).region
        )

        self.domain_name = api_gw2.DomainName(
            self,
            gen_name(self, "dn"),
            domain_name=domain_name,
            certificate=self.certificate
        )

        route53.ARecord(
            self,
            gen_name(self, "alias_record"),
            target=route53.RecordTarget.from_alias(route53_targets.ApiGatewayv2DomainProperties(
                regional_domain_name=self.domain_name.regional_domain_name,
                regional_hosted_zone_id=self.domain_name.regional_hosted_zone_id
            )),
            zone=self.hosted_zone,
            record_name=domain_name,
            comment=f"Alias record to map API gateway to custom domain name")

    def get_domain_mapping_options(self, mapping_key: Optional[str] = None) -> api_gw2.DomainMappingOptions:
        return api_gw2.DomainMappingOptions(domain_name=self.domain_name, mapping_key=mapping_key)


class DataIngestionApi(Construct):
    def __init__(self, scope: Construct, construct_id: str, *,
                 name: str,
                 description: str,
                 api_domain: ApiDomain = None,
                 domain_mapping_key: str = None) -> None:
        super().__init__(scope, construct_id)

        if api_domain is not None:
            domain_mapping = api_domain.get_domain_mapping_options(domain_mapping_key)
        else:
            domain_mapping = None

        self._api = api_gw2.HttpApi(self, 'api',
                                    api_name=name,
                                    description=description,
                                    default_domain_mapping=domain_mapping,
                                    disable_execute_api_endpoint=False)
        if api_domain is not None:
            self.url = self._api.default_stage.domain_url
        else:
            self.url = self._api.default_stage.url
        generate_output(self, f"{id}_url", self.url)

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


