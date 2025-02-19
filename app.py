#!/usr/bin/env python3
import os
import aws_cdk as cdk
from pubmed_search.pubmed_search_stack import PubmedSearchStack

app = cdk.App()

# コンテキストパラメータの設定
app.node.set_context("bucket_name", os.getenv("BUCKET_NAME", "my-pubmed-bucket"))
app.node.set_context("search_term", os.getenv("SEARCH_TERM", "sepsis"))

PubmedSearchStack(app, "PubmedSearchStack",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region=os.getenv('CDK_DEFAULT_REGION', 'ap-northeast-1')
    )
)

app.synth()
