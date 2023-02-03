import json
from constructs import Construct

import aws_cdk as cdk
from aws_cdk import (
    aws_ssm,
    SecretValue,
    aws_secretsmanager,
    aws_ec2,
    aws_iam,
    aws_redshift,
    aws_redshiftserverless
)
from typing import List

from .utils import (gen_name, generate_output)
from .aws_cloud_resources import (redshift_port_number)


class RedshiftBase(Construct):
    def __init__(
            self,
            scope: Construct,
            id: str,
            *,
            vpc: aws_ec2.Vpc = None,
            master_username: str,
            admin_password: str = None,
            **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Redshift IAM Role
        self.redshift_role = aws_iam.Role(
            self,
            gen_name(self, "DataLakeRedshiftClusterRole"),
            assumed_by=aws_iam.ServicePrincipal("redshift.amazonaws.com"),
            managed_policies=[
                aws_iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3ReadOnlyAccess"),
                aws_iam.ManagedPolicy.from_aws_managed_policy_name("AWSGlueConsoleFullAccess"),
                aws_iam.ManagedPolicy.from_aws_managed_policy_name("AmazonAthenaFullAccess"),
            ],
        )
        self.redshift_role.apply_removal_policy(cdk.RemovalPolicy.DESTROY)
        self.vpc = self._define_vpc(vpc)

        self.security_group = self.define_security_group()

        secret_name = "DataLakeClusterAdminPasswordSecret"
        self.cluster_secret = self.define_secret(name=secret_name,
                                                 username=master_username,
                                                 password=admin_password)
        self.password_secret_name = secret_name
        self.password_secret_key = "password"
        generate_output(self, "password_secret_name", self.password_secret_name)
        generate_output(self, "password_secret_key", self.password_secret_key)


    def define_secret(self, *,
                      name: str,
                      host: str = "no-host",
                      username: str,
                      password: str = None) -> aws_secretsmanager.Secret:
        secret_structure = {
            "engine": "redshift",
            "host": host,
            "username": username,
        }
        gen_secret = aws_secretsmanager.SecretStringGenerator(secret_string_template=json.dumps(secret_structure),
                                                              generate_string_key="password")
        set_secret = {
            "engine": "redshift",
            "host": host,
            "username": username,
            "password": SecretValue.unsafe_plain_text(password)
        }
        cluster_secret = aws_secretsmanager.Secret(
            self,
            gen_name(self, name),
            description=f"Redshift Cluster secret",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            secret_name=name,
            generate_secret_string=gen_secret if password is None else None,
            secret_object_value={**secret_structure, **set_secret} if password is not None else None)
        return cluster_secret


    def _define_vpc(self, vpc: aws_ec2.Vpc = None):
        if vpc is not None:
            return vpc

        result = self.define_vpc()
        result.apply_removal_policy(cdk.RemovalPolicy.DESTROY)
        return result

    def define_vpc(self):
        raise NotImplementedError()

    def define_security_group(self, ingress_peers: List[str] = []):
        # Create Security Group for Redshift
        result = aws_ec2.SecurityGroup(
            self,
            id=gen_name(self, "SecurityGroup"),
            vpc=self.vpc,
            security_group_name=f"redshift_sec_grp_{self.vpc.vpc_id}",
            description="Security Group for Redshift",
        )
        result.apply_removal_policy(cdk.RemovalPolicy.DESTROY)

        # Added n order to be able to run the lambda function redshift_schema_executor
        # maybe create a sg to lambda and then attach it to redshift serverless sg?
        result.add_ingress_rule(
            peer=result,
            connection=aws_ec2.Port.tcp(redshift_port_number),
            description="Allow Lambda functions access to the redshift serverless",
        )

        for peer in ingress_peers:
            result.add_ingress_rule(
                peer=aws_ec2.Peer.ipv4(peer),
                connection=aws_ec2.Port.tcp(redshift_port_number),
                description=f"Allow connections to the redshift cluster from '{peer}'",
            )

        return result


class RedshiftCluster(RedshiftBase):
    def define_vpc(self):
        return aws_ec2.Vpc(
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

    def __init__(
            self,
            scope: Construct,
            id: str,
            *,
            vpc: aws_ec2.Vpc = None,
            ec2_instance_type: str,
            db_name: str,
            master_username: str,
            admin_password: str = None,
            **kwargs):
        super().__init__(scope, id, vpc=vpc, master_username=master_username, admin_password=admin_password, **kwargs)

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

        master_password_secret = SecretValue.secrets_manager(self.password_secret_name,
                                                             json_field=self.password_secret_key)

        self.cluster = aws_redshift.CfnCluster(
            self,
            gen_name(self, "DataLakeRedshiftCluster"),
            cluster_type="single-node",
            # number_of_nodes=1,
            db_name=db_name,
            master_username=master_username,
            master_user_password=master_password_secret.to_string(),
            iam_roles=[self.redshift_role.role_arn],
            node_type=ec2_instance_type,
            cluster_subnet_group_name=redshift_cluster_subnet_group.ref,
            vpc_security_group_ids=[self.security_group.security_group_id],
            publicly_accessible=True,
        )
        self.cluster.apply_removal_policy(cdk.RemovalPolicy.DESTROY)
        self.cluster.add_depends_on(self.cluster_secret.node.default_child)


class RedshiftServerless(RedshiftBase):
    def define_vpc(self):
        # Redshift serverless need three subnets, each in one different AZ
        return aws_ec2.Vpc(
            self,
            gen_name(self, "DataLakeRedshiftVpc"),
            cidr="10.10.0.0/16",
            max_azs=3,
            nat_gateways=0,
            enable_dns_support=True,
            enable_dns_hostnames=True,
            subnet_configuration=[
                aws_ec2.SubnetConfiguration(
                    name="private", cidr_mask=24, subnet_type=aws_ec2.SubnetType.PRIVATE_ISOLATED
                ),
            ]
        )

    def __init__(
            self,
            scope: Construct,
            id: str,
            *,
            vpc: aws_ec2.Vpc = None,
            db_name: str,
            master_username: str,
            aws_region: str,
            admin_password: str = None,
            base_capacity: int = 32,
            max_query_execution_time: int = 360,
            **kwargs):
        super().__init__(scope, id, vpc=vpc, master_username=master_username, admin_password=admin_password, **kwargs)

        master_password_secret = SecretValue.secrets_manager(self.password_secret_name,
                                                             json_field=self.password_secret_key)
        self.redshift_namespace = aws_redshiftserverless.CfnNamespace(
            self,
            gen_name(self, "DataLakeRedshiftServerlessNamespace"),
            namespace_name="data-lake-namespace",
            admin_username=master_username,
            admin_user_password=master_password_secret.to_string(),
            db_name=db_name,
            iam_roles=[self.redshift_role.role_arn],
        )
        self.redshift_namespace.add_depends_on(self.cluster_secret.node.default_child)

        isolated_subnets = [subnet.subnet_id for subnet in self.vpc.isolated_subnets]

        # Set max query execution time. Default to 360 sec
        config_parameter_property = aws_redshiftserverless.CfnWorkgroup.ConfigParameterProperty(
            parameter_key="max_query_execution_time",
            parameter_value=str(max_query_execution_time)
        )

        self.redshift_workgroup = aws_redshiftserverless.CfnWorkgroup(
            self,
            gen_name(self, "DataLakeRedshiftServerlessWorkgroup"),
            workgroup_name="data-lake-workgroup",
            base_capacity=base_capacity,
            enhanced_vpc_routing=False,
            namespace_name=self.redshift_namespace.namespace_name,
            publicly_accessible=False,
            security_group_ids=[self.security_group.security_group_id],
            subnet_ids=isolated_subnets,
            config_parameters=[config_parameter_property]
        )

        self.redshift_workgroup.add_depends_on(self.redshift_namespace)
