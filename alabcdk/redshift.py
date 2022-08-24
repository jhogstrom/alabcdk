import secrets
from constructs import Construct

import aws_cdk as cdk
from aws_cdk import (
    aws_ssm,
    aws_ec2,
    aws_iam,
    aws_redshift,
    aws_redshiftserverless
)

from .utils import (gen_name)
from .aws_cloud_resources import (quick_sight_resources, redshift_port_number)


class RedshiftCluster(Construct):
    def __init__(
            self,
            scope: Construct,
            id: str,
            *,
            ec2_instance_type: str,
            db_name: str,
            master_username: str,
            admin_password: str = None,
            **kwargs):
        super().__init__(scope, id, **kwargs)

        # Redshift IAM Role
        self.redshift_cluster_role = aws_iam.Role(
            self,
            gen_name(self, "DataLakeRedshiftClusterRole"),
            assumed_by=aws_iam.ServicePrincipal("redshift.amazonaws.com"),
            managed_policies=[
                aws_iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3ReadOnlyAccess"),
                aws_iam.ManagedPolicy.from_aws_managed_policy_name("AWSGlueConsoleFullAccess"),
                aws_iam.ManagedPolicy.from_aws_managed_policy_name("AmazonAthenaFullAccess"),
            ],
        )
        self.redshift_cluster_role.apply_removal_policy(cdk.RemovalPolicy.DESTROY)

        # Cluster VPC
        self.vpc = aws_ec2.Vpc(
            self,
            gen_name(self, "DataLakeRedshiftVpc"),
            cidr="10.10.0.0/16",
            max_azs=2,
            nat_gateways=0,
            enable_dns_support=True,
            enable_dns_hostnames=True,
            subnet_configuration=[
                aws_ec2.SubnetConfiguration(
                    name="public", cidr_mask=24, subnet_type=aws_ec2.SubnetType.PUBLIC
                ),
                # aws_ec2.SubnetConfiguration(
                #     name="app", cidr_mask=24, subnet_type=aws_ec2.SubnetType.PRIVATE
                # ),
                aws_ec2.SubnetConfiguration(
                    # name="db", cidr_mask=24, subnet_type=aws_ec2.SubnetType.ISOLATED
                    name="db",
                    cidr_mask=24,
                    subnet_type=aws_ec2.SubnetType.PUBLIC,
                ),
            ],
        )
        self.vpc.apply_removal_policy(cdk.RemovalPolicy.DESTROY)

        # Subnet Group for Cluster
        redshift_cluster_subnet_group = aws_redshift.CfnClusterSubnetGroup(
            self,
            gen_name(self, "DataLakeRedshiftClusterSubnetGroup"),
            subnet_ids=self.vpc.select_subnets(
                subnet_type=aws_ec2.SubnetType.PUBLIC
            ).subnet_ids,
            description="Data Lake Redshift Cluster Subnet Group",
        )
        redshift_cluster_subnet_group.apply_removal_policy(cdk.RemovalPolicy.DESTROY)

        # Create Security Group for QuickSight
        self.quicksight_to_redshift_sg = aws_ec2.SecurityGroup(
            self,
            id="RedshiftQuicksightSecurityGroup",
            vpc=self.vpc,
            security_group_name=f"redshift_sec_grp_{self.vpc.vpc_id}",
            description="Security Group for Quicksight",
        )

        # https://docs.aws.amazon.com/quicksight/latest/user/regions.html
        self.quicksight_to_redshift_sg.add_ingress_rule(
            peer=aws_ec2.Peer.ipv4("52.210.255.224/27"),  # Value for Ireland region
            connection=aws_ec2.Port.tcp(5439),
            description="Allow QuickSight connections to the redshift cluster",
        )

        # Added n order to be able to run the lambda function redshift_schema_executor
        self.quicksight_to_redshift_sg.add_ingress_rule(
            peer=self.quicksight_to_redshift_sg,
            connection=aws_ec2.Port.tcp(5439),
            description="Allow Lambda functions access to the redshift cluster",
        )

        self.quicksight_to_redshift_sg.apply_removal_policy(cdk.RemovalPolicy.DESTROY)
        # Cluster credentials
        admin_password = admin_password or secrets.token_urlsafe(30)
        cluster_admin_password_ssm = aws_ssm.StringParameter(
            self,
            gen_name(self, "DataLakeClusterAdminPassword"),
            allowed_pattern=".*",
            description="DataLakeClusterAdminPassword",
            parameter_name="DataLakeClusterAdminPassword",
            string_value=admin_password,
        )
        cluster_admin_password_ssm.apply_removal_policy(cdk.RemovalPolicy.DESTROY)

        self.cluster = aws_redshift.CfnCluster(
            self,
            gen_name(self, "DataLakeRedshiftCluster"),
            cluster_type="single-node",
            # number_of_nodes=1,
            db_name=db_name,
            master_username=master_username,
            master_user_password=admin_password,
            iam_roles=[self.redshift_cluster_role.role_arn],
            node_type=ec2_instance_type,
            cluster_subnet_group_name=redshift_cluster_subnet_group.ref,
            vpc_security_group_ids=[self.quicksight_to_redshift_sg.security_group_id],
            publicly_accessible=True,
        )
        self.cluster.apply_removal_policy(cdk.RemovalPolicy.DESTROY)


class RedshiftServerless(Construct):
    def __init__(
            self,
            scope: Construct,
            id: str,
            db_name: str,
            master_username: str,
            aws_region: str,
            admin_password: str = None,
            base_capacity: int = 32,
            **kwargs):
        super().__init__(scope, id, **kwargs)

        # Redshift serverless need three subnets, each in one different AZ
        self.vpc = aws_ec2.Vpc(
            self,
            gen_name(self, "DataLakeRedshiftVpc"),
            cidr="10.10.0.0/16",
            max_azs=3,
            nat_gateways=0,
            enable_dns_support=True,
            enable_dns_hostnames=True,
            subnet_configuration=[
                aws_ec2.SubnetConfiguration(
                    name="public", cidr_mask=24, subnet_type=aws_ec2.SubnetType.PUBLIC
                ),
            ]
        )
        self.vpc.apply_removal_policy(cdk.RemovalPolicy.DESTROY)

        # Create Security Group for redshift serverless
        self.redshift_serverless_sg = aws_ec2.SecurityGroup(
            self,
            id="RedshiftServerlessSecurityGroup",
            vpc=self.vpc,
            security_group_name=f"redshift_sec_grp_{self.vpc.vpc_id}",
            description="Security Group for redshift",
        )

        self.redshift_serverless_sg.add_ingress_rule(
            peer=aws_ec2.Peer.ipv4(quick_sight_resources.get(aws_region).get("ip_address")),
            connection=aws_ec2.Port.tcp(redshift_port_number),
            description="Allow QuickSight connections to the redshift serverless",
        )

        # Added n order to be able to run the lambda function redshift_schema_executor
        # maybe create a sg to lambda and then attach it to redshift serverless sg?
        self.redshift_serverless_sg.add_ingress_rule(
            peer=self.redshift_serverless_sg,
            connection=aws_ec2.Port.tcp(redshift_port_number),
            description="Allow Lambda functions access to the redshift serverless",
        )

        self.redshift_serverless_sg.apply_removal_policy(cdk.RemovalPolicy.DESTROY)

        # Redshift IAM Role
        self.redshift_serverless_role = aws_iam.Role(
            self,
            gen_name(self, "DataLakeRedshiftServerlessRole"),
            assumed_by=aws_iam.ServicePrincipal("redshift.amazonaws.com"),
            managed_policies=[
                aws_iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3ReadOnlyAccess"),
                aws_iam.ManagedPolicy.from_aws_managed_policy_name("AWSGlueConsoleFullAccess"),
                aws_iam.ManagedPolicy.from_aws_managed_policy_name("AmazonAthenaFullAccess")  # dunno why
            ],
        )
        self.redshift_serverless_role.apply_removal_policy(cdk.RemovalPolicy.DESTROY)

        admin_password = admin_password or secrets.token_urlsafe(30)
        cluster_admin_password_ssm = aws_ssm.StringParameter(
            self,
            gen_name(self, "DataLakeDatabaseAdminPassword"),
            allowed_pattern=".*",
            description="DataLakeDatabaseAdminPassword",
            parameter_name="DataLakeDatabaseAdminPassword",
            string_value=admin_password,
        )
        cluster_admin_password_ssm.apply_removal_policy(cdk.RemovalPolicy.DESTROY)

        self.redshift_namespace = aws_redshiftserverless.CfnNamespace(
            self,
            gen_name(self, "DataLakeRedshiftServerlessNamespace"),
            namespace_name="data-lake-namespace",
            admin_username=master_username,
            admin_user_password=admin_password,
            db_name=db_name,
            iam_roles=[self.redshift_serverless_role.role_arn],
        )

        pub_subnets = [subnet.subnet_id for subnet in self.vpc.public_subnets]

        self.redshift_workgroup = aws_redshiftserverless.CfnWorkgroup(
            self,
            gen_name(self, "DataLakeRedshiftServerlessWorkgroup"),
            workgroup_name="data-lake-workgroup",
            base_capacity=base_capacity,
            enhanced_vpc_routing=False,
            namespace_name=self.redshift_namespace.namespace_name,
            publicly_accessible=True,
            security_group_ids=[self.redshift_serverless_sg.security_group_id],
            subnet_ids=pub_subnets,
        )
