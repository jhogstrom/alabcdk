from typing import Sequence
from constructs import Construct
from aws_cdk import (
    Duration,
    aws_iam,
    aws_route53,
    aws_route53_targets,
    aws_certificatemanager,
    aws_apigateway,
    aws_cloudfront,
    aws_cloudfront_origins,
    aws_s3,
)
from .s3 import Bucket
from .utils import (gen_name, get_params, filter_kwargs, generate_output)

class Website(Construct):
    def __init__(
            self,
            scope: Construct,
            id: str,
            *,
            index_document: str = None,
            error_document: str = None,
            # cors_rules: Sequence[aws_s3.CorsRule] = None,
            domain_name: str = None,
            hosted_zone_id: str = None,
            # backend: aws_apigateway.IRestApi = None,
            **kwargs) -> None:

        super().__init__(scope, id, **kwargs)
        index_document = index_document or "index.html"
        error_document = error_document or index_document
        kwargs = get_params(locals())
        s3_kwargs = filter_kwargs(kwargs, "s3_")
        cf_kwargs = filter_kwargs(kwargs, "cf_")
        # Set our own cloudfront defaults
        cf_kwargs.setdefault("price_class", aws_cloudfront.PriceClass.PRICE_CLASS_100)
        cf_kwargs.setdefault("comment", f"CDN for {id}/{gen_name(self, 'distro')}")
        cf_kwargs.setdefault("default_root_object", f"{index_document}")


        if domain_name and not hosted_zone_id:
            raise ValueError("If 'domain_name' is set, you also need to set 'hosted_zone_id'.")

        # routing_rules = []
        error_responses = []
        for error_code in ["403", "404"]:
            # routing_rules.append(
            #     aws_s3.RoutingRule(
            #         condition=aws_s3.RoutingRuleCondition(
            #             http_error_code_returned_equals=error_code,
            #         ),
            #         replace_key=aws_s3.ReplaceKey.prefix_with("#!")
            #     )
            # )
            error_responses.append(aws_cloudfront.ErrorResponse(
                http_status=int(error_code),
                response_page_path=f"/{index_document}",
                response_http_status=200,
                ttl=Duration.seconds(0)))

        # cors_rules = cors_rules or [aws_s3.CorsRule(
        #     allowed_methods=[aws_s3.HttpMethods.GET],
        #     allowed_headers=["*"],
        #     allowed_origins=["*"])]

        block_public_access = aws_s3.BlockPublicAccess.BLOCK_ALL if domain_name else None
        public_read_access = False if domain_name else True

        self.bucket = Bucket(
            self,
            "webcontent",
            block_public_access=block_public_access,
            public_read_access=public_read_access,
            **s3_kwargs)

        generate_output(self, f"{id}_url", self.bucket.bucket_website_url)
        if not domain_name:
            self.bucket.grant_public_access()
            return

        hosted_zone = aws_route53.HostedZone.from_hosted_zone_attributes(
            self,
            gen_name(self, "hosted_zone"),
            hosted_zone_id=hosted_zone_id,
            zone_name=domain_name
        )

        certificate = aws_certificatemanager.DnsValidatedCertificate(
            self,
            gen_name(self, "cert"),
            hosted_zone=hosted_zone,
            domain_name=domain_name,
            region="us-east-1"
            )

        oai = aws_cloudfront.OriginAccessIdentity(
            self,
            gen_name(self, "cf_oai"),
            comment=f"Origin Access Identity for {gen_name(self, id)}.")

        statement=aws_iam.PolicyStatement(
            resources=[self.bucket.arn_for_objects('*')],
            actions=["s3:GetObject"],
            principals=[aws_iam.CanonicalUserPrincipal(oai.cloud_front_origin_access_identity_s3_canonical_user_id)])

        self.bucket.add_to_resource_policy(statement)

        self.distribution = aws_cloudfront.Distribution(
            self,
            gen_name(self, "cdn"),
            default_behavior=aws_cloudfront.BehaviorOptions(
                origin=aws_cloudfront_origins.S3Origin(
                    self.bucket, origin_access_identity=oai),
                viewer_protocol_policy=aws_cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
            domain_names=[domain_name],
            error_responses=error_responses,
            certificate=certificate,
            **cf_kwargs
        )
        generate_output(self, "CDNUrl", self.distribution.distribution_domain_name)
        generate_output(self, "CDN_ID", self.distribution.distribution_id)

        aws_route53.ARecord(
            self,
            "CDN_ARecord",
            zone=hosted_zone,
            target=aws_route53.RecordTarget.from_alias(
                aws_route53_targets.CloudFrontTarget(self.distribution)))
        aws_route53.AaaaRecord(
            self,
            "CDN_AliasRecord",
            zone=hosted_zone,
            target=aws_route53.RecordTarget.from_alias(
                aws_route53_targets.CloudFrontTarget(self.distribution)))
