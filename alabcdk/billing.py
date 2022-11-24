from constructs import Construct
from aws_cdk import aws_budgets
from .utils import gen_name
from typing import List

# https://aws.amazon.com/aws-cost-management/aws-budgets/


class BillingAlert(Construct):

    def __init__(
            self,
            scope: Construct,
            id: str,
            *,
            emails_list: List[str] = None,
            threshold: int = None,
            **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        """
        Creates a billing alert which send notification to a set of emails if
        billing is over a threshold for a given month.

        params
        emails_list: list of email addresses to send email to
        threshold: Amount in USD to report when crossed
        """
        if emails_list is None or threshold is None:
            raise ValueError("emails_list and threshold needs to be defined for billing alerts!")

        subscribers_list = []
        for emails in emails_list:
            subscribers_list.append(
                aws_budgets.CfnBudget.SubscriberProperty(
                    address=emails,
                    subscription_type="EMAIL"
                )
            )

        prop = aws_budgets.CfnBudget.BudgetDataProperty(
            budget_type="COST",
            budget_limit=aws_budgets.CfnBudget.SpendProperty(
                amount=threshold,
                unit="USD"
            ),
            time_unit="MONTHLY",
        )

        self.budgets = aws_budgets.CfnBudget(
            self,
            id=gen_name(scope, f"budget-{threshold}"),
            budget=prop,
            notifications_with_subscribers=[
                aws_budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=aws_budgets.CfnBudget.NotificationProperty(
                        comparison_operator="GREATER_THAN",
                        notification_type="ACTUAL",
                        threshold=100,
                        threshold_type="PERCENTAGE"
                    ),
                    subscribers=subscribers_list
                )
            ]
        )
