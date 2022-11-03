from .utils import (generate_output)
from constructs import Construct
from aws_cdk import (
    Stack)
import subprocess
from typing import List


class AlabStack(Stack):
    def execute(self, cmd: str) -> str:
        with subprocess.Popen(cmd.split(), stdout=subprocess.PIPE) as proc:
            res = proc.stdout.read().decode().strip().replace("\t", " ").split("\n")
        return res

    def git_commit_id(self) -> str:
        return self.execute("git log --format='%H' -n 1")[0][1:-1]

    def git_remotes(self) -> List[str]:
        res = self.execute("git remote -v")
        return res

    def git_tag(self) -> str:
        return self.execute("git describe --always")[0][1:-1]

    def git_branch(self) -> str:
        return self.execute("git branch --show-current")[0]

    def add_deploy_info(self, add_git_info: bool) -> None:
        generate_output(self, "STAGE", self.stage)
        generate_output(self, "USER", self.user)
        if add_git_info:
            generate_output(self, "git_id", self.git_commit_id())
            generate_output(self, "git_tag", self.git_tag())
            generate_output(self, "git_branch", self.git_branch())
            for i, remote in enumerate(self.git_remotes()):
                generate_output(self, f"git_remote_{i}", remote)

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            *,
            stage: str = None,
            user: str = None,
            domain_name: str = None,
            hosted_zone: str = None,
            add_git_info: bool = True,
            **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.stage = stage or "DEV"
        self.user = user or "None"
        self.domain_name = domain_name
        self.hosted_zone = hosted_zone
        self.add_deploy_info(add_git_info)

    @property
    def _hosted_zone(self):
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
    def _domain_name(self):
        return f"{self.subdomain}.{self.base_domain}"