from constructs import Construct
from aws_cdk import (aws_backup, aws_events, aws_iam)
import aws_cdk as cdk
from .utils import gen_name

'''
Example how to use this module
test_bucket = create_bucket()

backup = BackupPlan(
        self,
        "id-test-backup",
        backup_resource_arn=test_bucket.bucket_arn,
        PITR_retention_period_days=13)

# Add some other backup rule
backup.add_backup_rule(cron_expression="15 14 * * ? *", retentation_period_days=34)

'''


class BackupPlan(aws_backup.BackupPlan):

    def __init__(
            self,
            scope: Construct,
            id: str,
            *,
            backup_resource_arn: str = None,
            vault: aws_backup.BackupVault = None,
            PITR_retention_period_days: int = None,
            **kwargs) -> None:
        if vault is None:
            vault = aws_backup.BackupVault(
                scope,
                gen_name(scope, f"{id}-backup-vault"),
                backup_vault_name=f"{id}-backup-vault")
        super().__init__(scope, id, backup_vault=vault, **kwargs)
        """
        Creates a backup for a specified backup_resource for s3 bucket.

        params
        backup_resource_arn: the arn of the resource to be backup
        vault: The backup vault to be used to store the backup. If None then a vault is created
        PITR_retention_period_days: If set, then point-in-time recovery (PITR) is enabled. Set the
        number of days to keep data.

        methods
        add_backup_rule: A backup rule which takes a cron expression and how long to keep this backup
        (retentation_period_days)


        """
        if PITR_retention_period_days is not None:
            self.add_rule(aws_backup.BackupPlanRule(
                rule_name=f"{id}-PITR-rule",
                enable_continuous_backup=True,
                delete_after=cdk.Duration.days(PITR_retention_period_days)))

        if backup_resource_arn is None:
            raise ValueError("One need to specify a backup resource!")

        # Create a role to attach to the selections resources
        self.role = aws_iam.Role(
            self,
            f"{id}-aws-backup-role",
            assumed_by=aws_iam.ServicePrincipal("backup.amazonaws.com"),
            managed_policies=[
                aws_iam.ManagedPolicy.from_managed_policy_arn(
                    self,
                    f"{id}-mp-s3-backup",
                    managed_policy_arn="arn:aws:iam::aws:policy/AWSBackupServiceRolePolicyForS3Backup",
                ),
                aws_iam.ManagedPolicy.from_managed_policy_arn(
                    self,
                    f"{id}-mp-s3-restore",
                    managed_policy_arn="arn:aws:iam::aws:policy/AWSBackupServiceRolePolicyForS3Restore",
                )
            ]
        )

        self.add_selection(
            f"{id}-backup-resource",
            resources=[aws_backup.BackupResource.from_arn(backup_resource_arn)],
            role=self.role)

    def add_backup_rule(self, cron_expression: str, retentation_period_days: int) -> None:
        '''
        cron expression according to
        https://docs.aws.amazon.com/lambda/latest/dg/services-cloudwatchevents-expressions.html
        e.g. "37 13 * * ? *"
        '''
        schedule = aws_events.Schedule.expression(f"cron({cron_expression})")
        self.add_rule(aws_backup.BackupPlanRule(
            schedule_expression=schedule,
            delete_after=cdk.Duration.days(retentation_period_days)))
