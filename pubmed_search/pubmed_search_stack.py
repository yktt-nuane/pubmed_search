from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    SecretValue,
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
)
from constructs import Construct

class PubmedSearchStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # コンテキストから値を取得
        bucket_name = self.node.try_get_context("bucket_name")
        search_term = self.node.try_get_context("search_term")
        openai_api_key = self.node.try_get_context("openai_api_key")
        gpt_model = self.node.try_get_context("gpt_model")

        # S3バケットの作成
        bucket = s3.Bucket(
            self,
            "PubmedDataBucket",
            bucket_name=bucket_name,
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

        # 論文取得用Lambda（既存）の実装
        request_layer = _lambda.LayerVersion.from_layer_version_arn(
            self,
            "RequestLayer",
            "arn:aws:lambda:ap-northeast-1:438774532845:layer:request_layer:2"
        )

        # 論文取得用Lambda実行ロール
        fetch_lambda_role = iam.Role(
            self,
            "PubmedFetchLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )

        # S3アクセス権限の追加
        fetch_lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:PutObject",
                    "s3:GetObject",
                ],
                resources=[f"{bucket.bucket_arn}/*"],
            )
        )

        # CloudWatch Logs権限の追加
        fetch_lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )

        # 論文取得用Lambda関数
        fetch_lambda = _lambda.Function(
            self,
            "PubmedSearchFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset("lambda"),
            role=fetch_lambda_role,
            timeout=Duration.seconds(300),
            memory_size=512,
            layers=[request_layer],
            environment={
                "BUCKET_NAME": bucket_name,
                "SEARCH_TERM": search_term,
            },
        )

        # 分析用Lambda実行ロール
        analyze_lambda_role = iam.Role(
            self,
            "PubmedAnalyzeLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )

        # S3アクセス権限の追加
        analyze_lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:PutObject",
                    "s3:GetObject",
                ],
                resources=[f"{bucket.bucket_arn}/*"],
            )
        )

        # CloudWatch Logs権限の追加
        analyze_lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )

        # OpenAIレイヤーの作成
        openai_layer = _lambda.LayerVersion(
            self,
            "OpenAILayer",
            code=_lambda.Code.from_asset("layers/openai"),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_11],
            description="OpenAI Python package layer for ChatGPT integration",
            compatible_architectures=[_lambda.Architecture.X86_64],
            removal_policy=RemovalPolicy.RETAIN
        )

        # 分析用Lambda関数
        analyze_lambda = _lambda.Function(
            self,
            "PubmedAnalyzeFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="analyze_function.lambda_handler",
            code=_lambda.Code.from_asset("analyze_lambda"),
            role=analyze_lambda_role,
            timeout=Duration.seconds(300),
            memory_size=1024,
            layers=[openai_layer],
            environment={
                "OPENAI_API_KEY": openai_api_key,
                "GPT_MODEL": gpt_model,
            },
        )

        # S3イベント通知の設定
        bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(analyze_lambda),
            s3.NotificationKeyFilter(suffix=".json")
        )

        # EventBridgeルールの作成
        rule = events.Rule(
            self,
            "DailyPubmedSearchRule",
            schedule=events.Schedule.cron(
                minute="5",
                hour="0",  # UTC 0:05 (JST 9:05)
            ),
        )

        # Lambda関数をターゲットとして追加
        rule.add_target(targets.LambdaFunction(fetch_lambda))
