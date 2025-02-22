from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
)
from constructs import Construct

class PubmedSearchStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3バケットの作成
        bucket = s3.Bucket(
            self,
            "PubmedDataBucket",
            bucket_name=self.node.try_get_context("bucket_name"),
            removal_policy=RemovalPolicy.RETAIN,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(90)
                        )
                    ]
                )
            ]
        )

        # Lambda実行ロールの作成
        lambda_role = iam.Role(
            self,
            "PubmedLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )

        # S3アクセス権限の追加
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:PutObject",
                    "s3:GetObject",
                ],
                resources=[f"{bucket.bucket_arn}/*"],
            )
        )

        # CloudWatch Logs権限の追加
        lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )

        # リクエストレイヤーの参照
        request_layer = _lambda.LayerVersion.from_layer_version_arn(
            self,
            "RequestLayer",
            "arn:aws:lambda:ap-northeast-1:438774532845:layer:request_layer:2"
        )

        # Lambda関数の作成
        pubmed_lambda = _lambda.Function(
            self,
            "PubmedSearchFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,  # Python 3.11に更新
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset("lambda"),
            role=lambda_role,
            timeout=Duration.seconds(300),
            memory_size=512,
            layers=[request_layer],  # レイヤーを追加
            environment={
                "BUCKET_NAME": bucket.bucket_name,
                "SEARCH_TERM": self.node.try_get_context("search_term"),
            },
        )

        # EventBridgeルールの作成（毎日実行）
        rule = events.Rule(
            self,
            "DailyPubmedSearchRule",
            schedule=events.Schedule.cron(
                minute="5",
                hour="0",  # UTC 0:05 (日本時間 9:05)
            ),
        )

        # Lambda関数をターゲットとして追加
        rule.add_target(targets.LambdaFunction(pubmed_lambda))
