from .utils import (generate_output)
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
        self.stage = stage or "DEV"
        self.user = user or "None"
        generate_output(self, "STAGE", self.stage)
        generate_output(self, "USER", self.user)

    @property
    def hosted_zone(self):
        res = self.node.try_get_context("hosted_zone")
        if res is None:
            raise ValueError("'hosted_zone' must be added to the context.")
        return res

    @property
    def workload_name(self):
        res = self.node.try_get_context("WORKLOAD")
        if res is None:
            raise ValueError("'WORKLOAD' must be added to the context.")
        return res

    @property
    def subdomain(self):
        res = self.node.try_get_context("SUBDOMAIN")
        if res is None:
            raise ValueError("'SUBDOMAIN' must be added to the context.")
        return res

    @property
    def base_domain(self):
        return self.node.try_get_context("BASEDOMAIN") or "aditrologistics.nu"

    @property
    def domain_name(self):
        return f"{self.subdomain}.{self.base_domain}"
