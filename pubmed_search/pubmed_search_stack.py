from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_notifications as s3n
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct


class PubmedSearchStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # コンテキストから値を取得
        bucket_name = self.node.try_get_context("bucket_name")
        openai_api_key = self.node.try_get_context("openai_api_key")
        gpt_model = self.node.try_get_context("gpt_model")
        search_terms_str = self.node.try_get_context("search_terms") or "sepsis,ards"
        search_terms = [term.strip() for term in search_terms_str.split(",")]

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
                            transition_after=Duration.days(90),
                        )
                    ]
                )
            ],
        )

        # 論文取得用Lambda（既存）の実装
        request_layer = _lambda.LayerVersion.from_layer_version_arn(
            self,
            "RequestLayer",
            "arn:aws:lambda:ap-northeast-1:438774532845:layer:request_layer:2",
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
                "SEARCH_TERMS": search_terms_str,
            },
        )

        # OpenAIレイヤーの作成
        openai_layer = _lambda.LayerVersion(
            self,
            "OpenAILayer",
            code=_lambda.Code.from_asset("layers/openai"),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_11],
            description="OpenAI Python package layer for ChatGPT integration",
            compatible_architectures=[_lambda.Architecture.X86_64],
            removal_policy=RemovalPolicy.RETAIN,
        )

        # 分析用Lambda実行ロール
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

        # 分析用Lambda関数
        analyze_lambda = _lambda.Function(
            self,
            "PubmedAnalyzeFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="analyze_function.lambda_handler",
            code=_lambda.Code.from_asset("analyze_lambda"),
            role=lambda_role,
            timeout=Duration.seconds(300),
            memory_size=1024,
            layers=[openai_layer],
            environment={
                "OPENAI_API_KEY": openai_api_key,
                "GPT_MODEL": gpt_model,
            },
        )

        # 翻訳用Lambda関数
        translate_lambda = _lambda.Function(
            self,
            "PubmedTranslateFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="translate_function.lambda_handler",
            code=_lambda.Code.from_asset("translate_lambda"),
            role=lambda_role,
            timeout=Duration.seconds(300),
            memory_size=1024,
            layers=[openai_layer],
            environment={
                "OPENAI_API_KEY": openai_api_key,
                "GPT_MODEL": gpt_model,
            },
        )

        # Step Functions用ロググループ
        log_group = logs.LogGroup(
            self,
            "PubmedWorkflowLogGroup",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Step Functions定義
        # 分析タスク
        analyze_task = tasks.LambdaInvoke(
            self,
            "AnalyzePapers",
            lambda_function=analyze_lambda,
            output_path="$.Payload",
            retry_on_service_exceptions=True,
            payload=sfn.TaskInput.from_object({"bucket": bucket.bucket_name, "key.$": "$.key"}),
        )

        # 翻訳タスク
        translate_task = tasks.LambdaInvoke(
            self,
            "TranslateToPapers",
            lambda_function=translate_lambda,
            output_path="$.Payload",
            retry_on_service_exceptions=True,
            payload=sfn.TaskInput.from_object(
                {"bucket": bucket.bucket_name, "output_key.$": "$.output_key"}
            ),
        )

        # 失敗状態
        fail_state = sfn.Fail(
            self,
            "FailState",
            cause="Workflow execution failed",
            error="WorkflowFailedError",
        )

        # ワークフロー定義
        definition = analyze_task.add_catch(
            errors=["States.ALL"], result_path="$.error", handler=fail_state
        ).next(
            translate_task.add_catch(
                errors=["States.ALL"], result_path="$.error", handler=fail_state
            )
        )

        # Step Functions ステートマシンの作成
        state_machine = sfn.StateMachine(
            self,
            "PubmedWorkflow",
            definition=definition,
            timeout=Duration.minutes(15),
            logs=sfn.LogOptions(
                destination=log_group,
                level=sfn.LogLevel.ALL,
                include_execution_data=True,
            ),
            tracing_enabled=True,
        )

        # Lambda関数への実行権限を付与
        analyze_lambda.grant_invoke(state_machine)
        translate_lambda.grant_invoke(state_machine)

        # S3トリガー用のLambdaロールを先に作成
        s3_trigger_lambda_role = iam.Role(
            self,
            "S3TriggerLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )

        # CloudWatch Logs権限の追加
        s3_trigger_lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )

        # S3からStep Functionsを起動するためのLambda
        s3_trigger_lambda = _lambda.Function(
            self,
            "S3TriggerFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=_lambda.Code.from_inline(
                """
import json
import boto3
import os

def handler(event, context):
    try:
        # S3イベントからバケットとキーを取得
        print(f"Received event: {json.dumps(event)}")
        bucket = event['Records'][0]['s3']['bucket']['name']
        key = event['Records'][0]['s3']['object']['key']

        # JSONファイルのみ処理
        if not key.endswith('.json') or key.endswith('_analysis.json') or key.endswith('_jp_analysis.json'):
            print(f"Skipping non-target file: {key}")
            return {'statusCode': 200, 'body': 'Not a target file'}

        # Step Functionsを起動
        client = boto3.client('stepfunctions')
        response = client.start_execution(
            stateMachineArn=os.environ['STATE_MACHINE_ARN'],
            input=json.dumps({
                'bucket': bucket,
                'key': key
            })
        )

        return {
            'statusCode': 200,
            'body': f"Started execution: {response['executionArn']}"
        }
    except Exception as e:
        print(f"Error: {str(e)}")
        return {'statusCode': 500, 'body': str(e)}
            """
            ),
            timeout=Duration.seconds(30),
            role=s3_trigger_lambda_role,  # ここで先に作成したロールを指定
            environment={"STATE_MACHINE_ARN": state_machine.state_machine_arn},
        )

        # Step Functionsの実行権限を付与
        state_machine.grant_start_execution(s3_trigger_lambda)

        # S3イベント通知の設定
        bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(s3_trigger_lambda),
            s3.NotificationKeyFilter(suffix=".json"),
        )

        # 各検索語ごとにEventBridgeルールを作成
        for i, term in enumerate(search_terms):
            rule = events.Rule(
                self,
                f"DailyPubmedSearchRule{i}",
                schedule=events.Schedule.cron(
                    minute="5",
                    hour=f"{i % 24}",
                ),
            )

            # Lambdaの入力パラメータを設定
            rule.add_target(
                targets.LambdaFunction(
                    fetch_lambda,
                    event=events.RuleTargetInput.from_object({"search_term": term}),
                )
            )

        # Lambda関数をターゲットとして追加
        rule.add_target(targets.LambdaFunction(fetch_lambda))

        # 週次エビデンス抽出用Lambda実行ロール
        weekly_lambda_role = iam.Role(
            self,
            "WeeklyEvidenceLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )

        # S3アクセス権限の追加
        weekly_lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:ListBucket",
                ],
                resources=[f"{bucket.bucket_arn}", f"{bucket.bucket_arn}/*"],
            )
        )

        # CloudWatch Logs権限の追加
        weekly_lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )

        # 週次エビデンス抽出用Lambda関数
        weekly_evidence_lambda = _lambda.Function(
            self,
            "WeeklyEvidenceFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="weekly_evidence_function.lambda_handler",
            code=_lambda.Code.from_asset("weekly_evidence_lambda"),
            role=weekly_lambda_role,
            timeout=Duration.seconds(300),
            memory_size=1024,
            layers=[openai_layer],
            environment={
                "BUCKET_NAME": bucket_name,
                "OPENAI_API_KEY": openai_api_key,
                "GPT_MODEL": gpt_model,
            },
        )

        # 週次実行用EventBridgeルール（毎週月曜日10時に実行）
        # セプシス用のEventBridgeルール（毎日実行）
        sepsis_rule = events.Rule(
            self,
            "DailySepsisSearchRule",
            schedule=events.Schedule.cron(
                minute="5",
                hour="0",  # UTC 0:05 (JST 9:05)
            ),
        )

        # セプシス用のルールにLambda関数をターゲットとして追加
        sepsis_rule.add_target(
            targets.LambdaFunction(
                fetch_lambda,
                event=events.RuleTargetInput.from_object({"search_term": "sepsis"}),
            )
        )

        # ARDS用のEventBridgeルール（毎日実行）
        ards_rule = events.Rule(
            self,
            "DailyArdsSearchRule",
            schedule=events.Schedule.cron(
                minute="15",  # 10分ずらす
                hour="0",  # UTC 0:15 (JST 9:15)
            ),
        )

        # ARDS用のルールにLambda関数をターゲットとして追加
        ards_rule.add_target(
            targets.LambdaFunction(
                fetch_lambda,
                event=events.RuleTargetInput.from_object({"search_term": "ards"}),
            )
        )

        # 週次エビデンス抽出用EventBridgeルール（セプシス用）
        weekly_sepsis_rule = events.Rule(
            self,
            "WeeklySepsisEvidenceRule",
            schedule=events.Schedule.cron(
                minute="0",
                hour="1",
                week_day="MON",
            ),
        )

        # セプシス用のルールにLambda関数をターゲットとして追加
        weekly_sepsis_rule.add_target(
            targets.LambdaFunction(
                weekly_evidence_lambda,
                event=events.RuleTargetInput.from_object({"search_term": "sepsis"}),
            )
        )

        # 週次エビデンス抽出用EventBridgeルール（ARDS用）
        weekly_ards_rule = events.Rule(
            self,
            "WeeklyArdsEvidenceRule",
            schedule=events.Schedule.cron(
                minute="15",  # 15分ずらす
                hour="1",
                week_day="MON",
            ),
        )

        # ARDS用のルールにLambda関数をターゲットとして追加
        weekly_ards_rule.add_target(
            targets.LambdaFunction(
                weekly_evidence_lambda,
                event=events.RuleTargetInput.from_object({"search_term": "ards"}),
            )
        )
