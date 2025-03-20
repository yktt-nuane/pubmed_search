import json
import os
import boto3
from openai import OpenAI
from datetime import datetime
from typing import Dict, List, Any, Optional
import tiktoken

# S3クライアント作成
s3 = boto3.client('s3')
# OpenAIクライアント作成
client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

def num_tokens_from_string(string: str, model: str = "gpt-4") -> int:
    """文字列のトークン数を計算"""
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(string))

def create_article_text(article: Dict[str, Any], pmid: str) -> str:
    """1つの論文データからテキストを生成"""
    return (
        f"PMID: {pmid}\n"
        f"Title: {article['title']}\n"
        f"Abstract: {article['abstract']}\n"
        f"Journal: {article['journal']}\n"
        f"Year: {article['publication_year']}\n\n"
    )

def chunk_articles(articles: Dict[str, Any], max_tokens: int = 4000) -> List[Dict[str, Any]]:
    """論文データを適切なサイズのチャンクに分割"""
    chunks = []
    current_chunk = {}
    current_tokens = 0
    base_prompt_tokens = num_tokens_from_string(get_analysis_prompt(""))

    for pmid, article in articles.items():
        article_text = create_article_text(article, pmid)
        article_tokens = num_tokens_from_string(article_text)

        # チャンクのトークン数が制限を超える場合、新しいチャンクを開始
        if current_tokens + article_tokens + base_prompt_tokens > max_tokens and current_chunk:
            chunks.append(current_chunk)
            current_chunk = {}
            current_tokens = 0

        current_chunk[pmid] = article
        current_tokens += article_tokens

    if current_chunk:
        chunks.append(current_chunk)

    return chunks

def get_analysis_prompt(text_for_prompt: str) -> str:
    """分析用のプロンプトを生成"""
    return f"""
You are a medical research expert. Analyze these academic articles and:
1) Identify the most impactful articles, prioritizing:
   - Articles published in high-impact journals (e.g., NEJM, Lancet, JAMA, Science, Nature, Cell, etc.)
   - Articles with groundbreaking findings or methodologies
   - Articles with significant clinical relevance
   - Studies with rigorous research designs (e.g., RCTs, well-designed cohort studies, systematic reviews)

2) For each selected article, provide:
   - Why it's impactful (novelty, methodology, clinical significance, journal reputation, etc.)
   - A concise summary (2-3 sentences)
   - Potential implications for clinical practice or future research

Articles to analyze:
{text_for_prompt}

Return your analysis in JSON format with the following structure for each article:
{{
    "pmid": string,
    "journal": string,
    "publication_year": string,
    "impact_reason": string,
    "summary": string,
    "implications": string
}}

Ensure all text fields are clear and concise. Select only articles with significant impact or from reputable journals. Quality over quantity is preferred.

IMPORTANT: If none of the articles meet the criteria for being impactful or from high-impact journals, return an empty array []. DO NOT select articles that lack significant impact or relevance just to provide a response.
"""

def analyze_papers_with_gpt(articles_data: Dict[str, Any], max_retries: int = 3) -> List[Dict[str, Any]]:
    """
    ChatGPT APIを使用して論文を分析し、インパクトの高い論文を抽出・要約する
    重要な論文がない場合は空のリストを返す
    """
    # 論文データをチャンクに分割
    chunks = chunk_articles(articles_data)
    all_results = []

    for chunk in chunks:
        try:
            # プロンプトの構築
            text_for_prompt = ""
            for pmid, article in chunk.items():
                text_for_prompt += create_article_text(article, pmid)

            prompt = get_analysis_prompt(text_for_prompt)

            # チャンクのトークン数を確認
            chunk_tokens = num_tokens_from_string(prompt)
            print(f"Chunk tokens: {chunk_tokens}")

            if chunk_tokens > 7000:  # 安全マージンを確保
                print(f"Skipping chunk with {chunk_tokens} tokens (too large)")
                continue

            # ChatGPT APIの呼び出し（リトライ付き）
            for retry in range(max_retries):
                try:
                    response = client.chat.completions.create(
                        model=os.environ.get('GPT_MODEL', 'gpt-4'),
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.2,
                        max_tokens=1000
                    )
                    break
                except Exception as e:
                    if retry == max_retries - 1:
                        raise
                    print(f"Retry {retry + 1}/{max_retries} due to error: {str(e)}")
                    continue

            # レスポンスのパース
            content = response.choices[0].message.content
            chunk_results = json.loads(content)
            if isinstance(chunk_results, list):
                all_results.extend(chunk_results)
            else:
                all_results.append(chunk_results)

        except Exception as e:
            print(f"Error processing chunk: {str(e)}")
            continue

    # 空のリストでなければ、最大3つの論文を選択
    if all_results:
        return sorted(all_results, key=lambda x: len(x.get('impact_reason', '')), reverse=True)[:3]
    else:
        return []

def get_s3_object_from_event(event: Dict) -> Optional[tuple[str, str]]:
    """イベントからS3バケット名とキーを取得"""
    try:
        # Step Functionsからの直接入力
        if 'bucket' in event and 'key' in event:
            return (event['bucket'], event['key'])

        # S3イベント
        if 'Records' in event:
            record = event['Records'][0]
            if record.get('eventSource') == 'aws:s3':
                return (
                    record['s3']['bucket']['name'],
                    record['s3']['object']['key']
                )

        return None
    except Exception as e:
        print(f"Error parsing event: {str(e)}")
        return None

def lambda_handler(event, context):
    try:
        print(f"Received event: {json.dumps(event)}")

        # S3オブジェクト情報の取得
        s3_info = get_s3_object_from_event(event)
        if not s3_info:
            return {
                "statusCode": 400,
                "body": {
                    "error": "Invalid event structure",
                    "message": "Expected S3 event or direct bucket/key specification."
                }
            }

        bucket, key = s3_info
        print(f"Processing s3://{bucket}/{key}")

        # S3から論文データを取得
        response = s3.get_object(Bucket=bucket, Key=key)
        pubmed_data = json.loads(response['Body'].read().decode('utf-8'))

        if not isinstance(pubmed_data, dict) or 'articles' not in pubmed_data:
            return {
                "statusCode": 400,
                "body": {
                    "error": "Invalid file format",
                    "message": "Expected JSON with 'articles' field."
                }
            }

        # ChatGPTによる分析
        analysis_results = analyze_papers_with_gpt(pubmed_data['articles'])

        # 出力JSONの作成
        output_json = {
            "metadata": {
                "original_file": f"s3://{bucket}/{key}",
                "analysis_date": datetime.now().isoformat(),
                "search_term": pubmed_data.get('metadata', {}).get('search_term', 'unknown'),
                "total_analyzed": len(pubmed_data['articles']),
                "total_selected": len(analysis_results)
            },
            "impactful_articles": analysis_results
        }

        # 分析結果をS3に保存
        output_key = key.replace('.json', '_analysis.json')
        s3.put_object(
            Bucket=bucket,
            Key=output_key,
            Body=json.dumps(output_json, ensure_ascii=False, indent=2),
            ContentType="application/json"
        )

        # Step Functions用の出力
        return {
            "statusCode": 200,
            "bucket": bucket,
            "input_key": key,
            "output_key": output_key,
            "articles_analyzed": len(pubmed_data['articles']),
            "articles_selected": len(analysis_results)
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "error": "Error processing request",
            "details": str(e)
        }
