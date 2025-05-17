import json
import os
from datetime import datetime
from typing import Any, Dict

import boto3
from openai import OpenAI

# S3クライアント作成
s3 = boto3.client("s3")
# OpenAIクライアント作成
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def get_translation_prompt(analysis_data: Dict[str, Any]) -> str:
    """
    翻訳用のプロンプトを生成
    """
    # 論文情報をJSON形式に変換
    analysis_json = json.dumps(analysis_data, ensure_ascii=False)

    return f"""
あなたは医学研究の専門家です。以下のJSONデータを日本語に翻訳してください。
JSONの構造を維持し、内容のみを日本語に翻訳してください。
医学用語は適切な日本語の専門用語に翻訳し、必要に応じて英語の原語も括弧内に残してください。

各フィールドの翻訳指示:
- pmid: 翻訳不要
- journal: 翻訳不要（ジャーナル名はそのまま）
- publication_year: 翻訳不要
- impact_reason: インパクトの理由を日本語に翻訳
- summary: 要約を日本語に翻訳
- implications: 含意・影響を日本語に翻訳

翻訳対象のJSONデータ:
{analysis_json}

JSON形式で返答してください。キー名は英語のまま維持し、値のみを日本語に翻訳してください。
"""


def lambda_handler(event, context):
    try:
        print(f"Received event: {json.dumps(event)}")

        # Step Functionsからのパラメータ取得
        bucket = event.get("bucket")
        input_key = event.get("output_key")

        # 直接S3イベントからの場合も対応
        if "Records" in event:
            bucket = event["Records"][0]["s3"]["bucket"]["name"]
            input_key = event["Records"][0]["s3"]["object"]["key"]

        if not bucket or not input_key:
            return {
                "statusCode": 400,
                "body": json.dumps(
                    {
                        "error": "Missing required parameters",
                        "message": "Both 'bucket' and 'output_key' are required.",
                    }
                ),
            }

        print(f"Processing s3://{bucket}/{input_key}")

        # S3から分析済み論文データを取得
        response = s3.get_object(Bucket=bucket, Key=input_key)
        analysis_data = json.loads(response["Body"].read().decode("utf-8"))

        # ChatGPTによる翻訳
        prompt = get_translation_prompt(analysis_data)

        response = client.chat.completions.create(
            model=os.environ.get("GPT_MODEL", "gpt-4"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2000,
        )

        # レスポンスのパース
        content = response.choices[0].message.content

        # JSONを抽出（余分なテキストがある場合の対策）
        import re

        json_match = re.search(r"({[\s\S]*})", content)
        if json_match:
            content = json_match.group(1)

        translated_data = json.loads(content)

        # 元データのメタデータを拡張
        if "metadata" in translated_data:
            translated_data["metadata"]["translation_date"] = datetime.now().isoformat()
            translated_data["metadata"]["original_language"] = "en"
            translated_data["metadata"]["target_language"] = "ja"

        # 翻訳結果をS3に保存
        output_key = input_key.replace("_analysis.json", "_jp_analysis.json")
        s3.put_object(
            Bucket=bucket,
            Key=output_key,
            Body=json.dumps(translated_data, ensure_ascii=False, indent=2),
            ContentType="application/json",
        )

        return {
            "statusCode": 200,
            "bucket": bucket,
            "input_key": input_key,
            "output_key": output_key,
            "message": "Translation completed successfully",
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "error": "Error processing request",
            "details": str(e),
        }
