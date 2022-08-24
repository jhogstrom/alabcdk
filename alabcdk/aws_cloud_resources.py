redshift_port_number = 5439

# See: https://docs.aws.amazon.com/quicksight/latest/user/regions.html
quick_sight_resources = {
    "us-east-2": {"website_user_access": "https://us-east-2.quicksight.aws.amazon.com",
                  "service_api_point": "quicksight.us-east-2.amazonaws.com",
                  "ip_address": "52.15.247.160/27"},
    "eu-west-1": {"website_user_access": "https://eu-west-1.quicksight.aws.amazon.com",
                  "service_api_point": "quicksight.eu-west-1.amazonaws.com",
                  "ip_address": "52.210.255.224/27"},
}
