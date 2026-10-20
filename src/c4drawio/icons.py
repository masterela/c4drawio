"""AWS icon names (bundled list from draw.io) and AWS category colours."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

COMPUTE, STORAGE, DATABASE, NETWORK, APPINT, MGMT, SECURITY, ML, ANALYTICS, DEVTOOLS, MIGRATION, IOT = (
    "#ED7100", "#7AA116", "#C925D1", "#8C4FFF", "#E7157B", "#E7157B", "#DD344C", "#01A88D", "#8C4FFF", "#C925D1",
    "#01A88D", "#3F8624",
)
_CATEGORIES = [
    (COMPUTE, "lambda ec2 batch ecs fargate ecr eks elastic_beanstalk lightsail app_runner spot_instance auto_scaling2 "
             "outposts elastic_container_service elastic_kubernetes_service elastic_container_registry"),
    (STORAGE, "s3 simple_storage_service efs elastic_file_system storage_gateway backup fsx s3_glacier "
             "elastic_block_store"),
    (DATABASE, "dynamodb aurora rds elasticache documentdb_with_mongodb_compatibility neptune timestream keyspaces "
              "memorydb_for_redis"),
    (NETWORK, "vpc cloudfront route_53 direct_connect transit_gateway elastic_load_balancing network_load_balancer "
             "application_load_balancer vpc_privatelink global_accelerator site_to_site_vpn client_vpn "
             "virtual_private_cloud"),
    (APPINT, "api_gateway step_functions eventbridge sns sqs mq appsync simple_notification_service "
            "simple_queue_service"),
    (MGMT, "cloudwatch cloudwatch_2 cloudformation systems_manager cloudtrail config organizations control_tower "
          "service_catalog"),
    (SECURITY, "iam identity_and_access_management single_sign_on key_management_service secrets_manager guardduty "
              "waf shield cognito security_hub certificate_manager inspector macie iam_identity_center"),
    (ML, "sagemaker sagemaker_model bedrock comprehend rekognition textract machine_learning translate polly kendra"),
    (ANALYTICS, "glue athena quicksight lake_formation kinesis emr redshift opensearch_service "
               "managed_streaming_for_kafka data_pipeline"),
    (DEVTOOLS, "codebuild codecommit codedeploy codepipeline codestar cloud9 xray"),
    (MIGRATION, "database_migration_service datasync migration_hub transfer_family snowball"),
]
CATEGORY_COLOR = {name: color for color, names in _CATEGORIES for name in names.split()}
DEFAULT_ICON_COLOR = "#232F3E"

# Plain glyphs (not "resource icons"): drawn without a coloured square background.
GLYPHS = {
    "users", "user", "client", "mobile_client", "traditional_server", "corporate_data_center", "internet",
    "internet_alt1", "internet_alt2", "generic_database", "generic_firewall", "office_building", "servers",
    "disk", "documents", "email", "forums", "multimedia", "folder", "folders", "gear", "alert", "chat",
}


@lru_cache(maxsize=1)
def aws_icons() -> list[str]:
    p = Path(__file__).with_name("aws_icons.txt")
    return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def icon_color(name: str) -> str:
    return CATEGORY_COLOR.get(name, DEFAULT_ICON_COLOR)


def search(term: str = "") -> list[str]:
    t = term.lower().replace(" ", "_")
    return [n for n in aws_icons() if t in n]
