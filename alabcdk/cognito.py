import os
from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    aws_cognito,
    aws_certificatemanager,
    aws_route53,
    aws_route53_targets
)
from .utils import (
    gen_name,
    get_params,
    remove_params,
    stage_based_removal_policy,
    generate_output)


class Cognito(Construct):
    """
    Creates a Cognito user pool and user pool client.
    """
    def _findfile(filename):
        if not filename:
            return None
        if os.path.exists(filename):
            return filename
        if os.path.exists(os.path.join(os.path.dirname(__file__), filename)):
            return os.path.join(os.path.dirname(__file__), filename)
        raise FileNotFoundError(f"File '{filename}' not found")

    def __init__(
            self,
            scope: Construct,
            id: str,
            *,
            domain_name: str,
            hosted_zone_id: str,
            metadata_filename: str,
            cloudfront_alias_record: aws_route53.ARecord,
            certificate: aws_certificatemanager.ICertificate = None,
            **kwargs) -> None:

        super().__init__(scope, id, **kwargs)

        # COGNITO USER POOL (UP)
        userpool = aws_cognito.UserPool(
            self,
            gen_name(self, f"{id}userpool", all_lower=True),
            self_sign_up_enabled=False,
            sign_in_aliases={"email": True},
            auto_verify=aws_cognito.AutoVerifiedAttrs(email=True),
            removal_policy=cdk.RemovalPolicy.DESTROY,
            standard_attributes=aws_cognito.StandardAttributes(
                email=aws_cognito.StandardAttribute(required=True),
                phone_number=aws_cognito.StandardAttribute(required=True),
                family_name=aws_cognito.StandardAttribute(required=True),
                given_name=aws_cognito.StandardAttribute(required=True),
            ),
            user_pool_name=id,
        )

        # COGNITO UP DOMAIN
        cognito_auth_url = "auth." + domain_name
        # Move this to the website construct and create the cert for "*.<domain>"
        auth_certificate = certificate or aws_certificatemanager.DnsValidatedCertificate(
            self,
            gen_name(self, "cert"),
            hosted_zone=hosted_zone_id,
            domain_name=cognito_auth_url,
            region="us-east-1",
            )

        user_pool_domain = userpool.add_domain(
            gen_name(self, f"{id}domain"),
            custom_domain=aws_cognito.CustomDomainOptions(
                certificate=auth_certificate,
                domain_name=cognito_auth_url),
        )

        user_pool_domain.node.add_dependency(cloudfront_alias_record)

        # # ROUTE53 COGNITO ALIAS
        aws_route53.ARecord(
            self,
            gen_name(self, f"{id}_portal"),
            record_name=cognito_auth_url,
            zone=hosted_zone_id,
            target=aws_route53.RecordTarget.from_alias(
                aws_route53_targets.UserPoolDomainTarget(user_pool_domain)),
            comment="Portal Auth URL"
        )

        # COGNITO UP IDP
        # Note: The 'cognito.UserPoolIdentityProviderSaml' is not natively supported yet
        # Issue: https://github.com/aws/aws-cdk/issues/6853
        supported_idps = []
        filename = self._findfile(metadata_filename)
        if filename:
            with open(filename, "r") as f:
                samlfilecontent = f.read()
            userpool_saml_idp = aws_cognito.CfnUserPoolIdentityProvider(
                self,
                gen_name(self, f"{id}_saml_idp"),
                user_pool_id=userpool.user_pool_id,
                provider_type="SAML",
                provider_name=gen_name(self, f"{id}_samluserpool"),
                provider_details={"MetadataFile": samlfilecontent},
                attribute_mapping={
                    'email': 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress',
                    'family_name': 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname',
                    'given_name': 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname',
                    'preferred_username': 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name', # upn
                    #  additional
                    'custom:groups': 'http://schemas.microsoft.com/ws/2008/06/identity/claims/groups',
                    'custom:employee_id': 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/employeeid',
                    'custom:job_title': 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/jobtitle',
                    'custom:company_name': 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/companyname',
                }
            )
            supported_idps.append(aws_cognito.UserPoolClientIdentityProvider.custom(userpool_saml_idp.provider_name))

        if not supported_idps:
            supported_idps.append(aws_cognito.UserPoolClientIdentityProvider.COGNITO)

        # COGNITO UP CLIENT
        client_name = "cognitodemo"
        userpool_client = userpool.add_client(
            gen_name(self, f"{id}client"),
            user_pool_client_name=client_name,
            supported_identity_providers=supported_idps,
            o_auth=aws_cognito.OAuthSettings(
                flows=aws_cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[
                    aws_cognito.OAuthScope.OPENID,
                    aws_cognito.OAuthScope.PROFILE,
                    aws_cognito.OAuthScope.EMAIL],
                callback_urls=[f"https://{cloudfront_alias_record.domain_name}"],
                logout_urls=[f"https://{cloudfront_alias_record.domain_name}"],
            ),
        )

        if userpool_saml_idp:
            userpool_client.node.add_dependency(userpool_saml_idp)


        #     # COGNITO UI CUSTOMIZATION
        #     cognitoUiCustomsEnabled = False
        #     if cognitoUiCustomsEnabled:
        #         cssfilecontent = "" # Read from file
        #         aws_cognito.CfnUserPoolUICustomizationAttachment(
        #             self,
        #             "cognitoUiCustoms",
        #             client_id=userpool_client.user_pool_client_id,
        #             user_pool_id=userpool.user_pool_id,
        #             css=cssfilecontent,
        #         )
        #     alabcdk.generate_output(self, "cognitoUserPoolClientId", userpool_client.user_pool_client_id)

        # alabcdk.generate_output(self, "cognitoUserPoolId", userpool.user_pool_id)
