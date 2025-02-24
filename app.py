#!/usr/bin/env python3
import os
from dotenv import load_dotenv
import aws_cdk as cdk
from pubmed_search.pubmed_search_stack import PubmedSearchStack

# .envファイルの読み込み
load_dotenv(override=True)

# 必須環境変数のチェック
required_env_vars = ['BUCKET_NAME', 'OPENAI_API_KEY']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Required environment variables are missing: {', '.join(missing_vars)}")

app = cdk.App()

# コンテキストパラメータの設定
app.node.set_context("bucket_name", os.getenv("BUCKET_NAME").lower())
app.node.set_context("search_term", os.getenv("SEARCH_TERM", "sepsis"))
app.node.set_context("openai_api_key", os.getenv("OPENAI_API_KEY"))
app.node.set_context("gpt_model", os.getenv("GPT_MODEL", "gpt-4"))

PubmedSearchStack(app, "PubmedSearchStack",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region=os.getenv('CDK_DEFAULT_REGION', 'ap-northeast-1')
    )
)

app.synth()
