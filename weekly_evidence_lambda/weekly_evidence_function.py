import json
import os
import boto3
from openai import OpenAI
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import re

# S3クライアント作成
s3 = boto3.client('s3')
# OpenAIクライアント作成
client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

# CQのリスト
CQ_LIST = [
    {
        "id": "CQ4-1",
        "question": "敗血症に対して，PMX-DHPを行うか?",
        "keywords": ["PMX-DHP", "polymyxin B", "endotoxin adsorption", "polymyxin B-immobilized fiber", "トレミキシン"]
    },
    {
        "id": "CQ4-2",
        "question": "敗血症性AKIに対して，早期の腎代替療法を行うか?",
        "keywords": ["early RRT", "early renal replacement therapy", "early dialysis", "early CRRT", "早期腎代替療法"]
    },
    {
        "id": "CQ4-3",
        "question": "敗血症性AKIに対する腎代替療法では持続的治療を行うか?",
        "keywords": ["CRRT", "continuous renal replacement therapy", "continuous venovenous hemodiafiltration", "CVVHDF", "持続的腎代替療法"]
    },
    {
        "id": "CQ4-4",
        "question": "敗血症性AKIに対する腎代替療法において，血液浄化量の増加を行うか?",
        "keywords": ["high-volume hemofiltration", "high-dose CRRT", "intensive renal support", "high-intensity CRRT", "高容量血液浄化"]
    }
]

def get_files_from_last_week(bucket_name: str) -> List[str]:
    """
    過去1週間分の解析済み論文ファイル（_analysis.json）を取得
    """
    # 1週間前の日付を計算
    one_week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    try:
        # S3バケット内のファイル一覧を取得
        response = s3.list_objects_v2(Bucket=bucket_name)

        if 'Contents' not in response:
            return []

        analysis_files = []

        for obj in response['Contents']:
            # _analysis.jsonのファイルを対象とする（_jp_analysis.jsonは除外）
            if obj['Key'].endswith('_analysis.json') and not obj['Key'].endswith('_jp_analysis.json'):
                # 最終更新日が1週間以内のファイルを選択
                if obj['LastModified'].strftime('%Y-%m-%d') >= one_week_ago:
                    analysis_files.append(obj['Key'])

        return analysis_files

    except Exception as e:
        print(f"Error fetching files from S3: {str(e)}")
        return []

def extract_evidence_articles(articles_data: List[Dict[str, Any]], cq_list: List[Dict]) -> Dict[str, List]:
    """
    GPT APIを使用して、CQに関連するエビデンス論文を抽出
    """
    prompt = create_evidence_extraction_prompt(articles_data, cq_list)

    try:
        # ChatGPT APIの呼び出し
        response = client.chat.completions.create(
            model=os.environ.get('GPT_MODEL', 'gpt-4'),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2000
        )

        # レスポンスのパース
        content = response.choices[0].message.content

        # JSONを抽出（余分なテキストがある場合の対策）
        json_match = re.search(r'({[\s\S]*})', content)
        if json_match:
            content = json_match.group(1)

        return json.loads(content)

    except Exception as e:
        print(f"Error calling OpenAI API: {str(e)}")
        return {}

def create_evidence_extraction_prompt(articles_data: List[Dict[str, Any]], cq_list: List[Dict]) -> str:
    """
    エビデンス抽出用のプロンプトを生成
    """
    articles_json = json.dumps(articles_data, ensure_ascii=False)
    cq_json = json.dumps(cq_list, ensure_ascii=False)

    return f"""
あなたは敗血症研究の専門家です。提供された論文データを分析し、特定の臨床課題（CQ）に関連するエビデンスとなる論文を抽出してください。

## 分析対象の論文データ
{articles_json}

## 臨床課題（CQ）
{cq_json}

## 指示
1. 各CQについて、関連するエビデンスとなり得る論文を抽出してください。
2. 論文が該当するかの判断基準:
   - 論文のタイトルまたはアブストラクトに関連キーワードが含まれている
   - 研究内容がCQに直接関連している
   - エビデンスレベルが比較的高い研究（RCT、メタ分析、システマティックレビューなど）が特に重要
   - インパクトファクターの高いジャーナル（NEJM, Lancet, JAMA, Natureなど）の論文を優先
3. 各CQごとに、見つかった論文のPMID、ジャーナル名、出版年、タイトル、要約、エビデンスとしての価値を含めてください。
4. CQに関連する論文が見つからない場合は、そのCQについては空の配列を返してください。

以下のJSON形式で返答してください:
{{
  "CQ4-1": [
    {{
      "pmid": "論文のPMID",
      "journal": "ジャーナル名",
      "publication_year": "出版年",
      "title": "論文のタイトル",
      "summary": "論文の簡潔な要約",
      "evidence_value": "この論文がCQに対するエビデンスとしての価値についての説明"
    }}
  ],
  "CQ4-2": [],  // 関連論文がない場合
  "CQ4-3": [...],
  "CQ4-4": [...]
}}
"""

def lambda_handler(event, context):
    try:
        print(f"Weekly evidence extraction started at {datetime.now().isoformat()}")

        # バケット名を取得
        bucket_name = os.environ.get('BUCKET_NAME')
        if not bucket_name:
            raise ValueError("BUCKET_NAME environment variable is not set")

        # 過去1週間の解析済みファイルを取得
        analysis_files = get_files_from_last_week(bucket_name)
        print(f"Found {len(analysis_files)} analysis files from last week")

        if not analysis_files:
            print("No files to process. Exiting.")
            return {
                "statusCode": 200,
                "message": "No files to process"
            }

        # 全ての論文データを取得
        all_articles = []
        for file_key in analysis_files:
            try:
                response = s3.get_object(Bucket=bucket_name, Key=file_key)
                file_data = json.loads(response['Body'].read().decode('utf-8'))

                # impactful_articles配列から論文データを取得
                if 'impactful_articles' in file_data:
                    all_articles.extend(file_data['impactful_articles'])
            except Exception as e:
                print(f"Error processing file {file_key}: {str(e)}")
                continue

        print(f"Total articles to analyze: {len(all_articles)}")

        if not all_articles:
            print("No articles found in the analysis files. Exiting.")
            return {
                "statusCode": 200,
                "message": "No articles found"
            }

        # CQに関連するエビデンス論文を抽出
        evidence_results = extract_evidence_articles(all_articles, CQ_LIST)

        # 結果にエビデンスがあるか確認
        has_evidence = False
        for cq_id in evidence_results:
            if evidence_results[cq_id] and len(evidence_results[cq_id]) > 0:
                has_evidence = True
                break

        if not has_evidence:
            print("No evidence articles found for any CQ. Exiting without creating a file.")
            return {
                "statusCode": 200,
                "message": "No evidence articles found"
            }

        # 出力JSONの作成
        output_json = {
            "metadata": {
                "generated_date": datetime.now().isoformat(),
                "period_start": (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
                "period_end": datetime.now().strftime('%Y-%m-%d'),
                "files_analyzed": len(analysis_files),
                "articles_analyzed": len(all_articles)
            },
            "evidence_articles": evidence_results
        }

        # 結果をS3に保存
        date_str = datetime.now().strftime("%Y%m%d")
        output_key = f"weekly_evidence_{date_str}.json"

        s3.put_object(
            Bucket=bucket_name,
            Key=output_key,
            Body=json.dumps(output_json, ensure_ascii=False, indent=2),
            ContentType="application/json"
        )

        print(f"Weekly evidence report saved to s3://{bucket_name}/{output_key}")

        return {
            "statusCode": 200,
            "message": "Weekly evidence extraction completed successfully",
            "output_file": output_key
        }

    except Exception as e:
        print(f"Error in weekly evidence extraction: {str(e)}")
        return {
            "statusCode": 500,
            "error": "Error processing request",
            "details": str(e)
        }
