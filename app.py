#!/usr/bin/env python3
import os

import aws_cdk as cdk
from dotenv import load_dotenv

from pubmed_search.pubmed_search_stack import PubmedSearchStack

# .envファイルの読み込み
load_dotenv(override=True)

# 必須環境変数のチェック
required_env_vars = ["BUCKET_NAME", "OPENAI_API_KEY"]
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Required environment variables are missing: {', '.join(missing_vars)}")

app = cdk.App()

# バケット名を取得
bucket_name = os.getenv("BUCKET_NAME")
# この時点でバケット名がNoneでないことをtype checkerに伝える
assert bucket_name is not None, "BUCKET_NAME should not be None at this point"

# コンテキストパラメータの設定
app.node.set_context("bucket_name", bucket_name.lower())
app.node.set_context("openai_api_key", os.getenv("OPENAI_API_KEY"))
app.node.set_context("gpt_model", os.getenv("GPT_MODEL", "gpt-4"))

# 注意: search_termsはCDKスタック内でハードコード（sepsis, ards）されているため、
# 環境変数からの設定は不要

PubmedSearchStack(
    app,
    "PubmedSearchStack",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION", "ap-northeast-1"),
    ),
)

app.synth()
