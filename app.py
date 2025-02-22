#!/usr/bin/env python3
import os
from dotenv import load_dotenv  # python-dotenvを使用
import aws_cdk as cdk
from pubmed_search.pubmed_search_stack import PubmedSearchStack

# .envファイルの読み込み
load_dotenv(override=True)

# 必須環境変数のチェック
bucket_name = os.getenv("BUCKET_NAME")
if not bucket_name:
    raise ValueError("BUCKET_NAME environment variable is required")

app = cdk.App()

# コンテキストパラメータの設定
app.node.set_context("bucket_name", bucket_name.lower())  # 確実に小文字に変換
app.node.set_context("search_term", os.getenv("SEARCH_TERM", "sepsis"))

PubmedSearchStack(app, "PubmedSearchStack",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region=os.getenv('CDK_DEFAULT_REGION', 'ap-northeast-1')
    )
)

app.synth()
