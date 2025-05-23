import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List

import boto3
import tiktoken
from openai import OpenAI

# S3クライアント作成
s3 = boto3.client("s3")
# OpenAIクライアント作成
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def num_tokens_from_string(string: str, model: str = "gpt-4") -> int:
    """文字列のトークン数を計算"""
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(string))


def get_files_from_last_week(bucket_name: str, search_term: str = None) -> List[str]:
    """
    過去1週間分の解析済み論文ファイル（_analysis.json）を取得
    search_termが指定されている場合は、その検索語に関連するファイルのみ返す
    """
    # 1週間前の日付を計算
    one_week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    try:
        # S3バケット内のファイル一覧を取得
        response = s3.list_objects_v2(Bucket=bucket_name)

        if "Contents" not in response:
            return []

        analysis_files = []

        for obj in response["Contents"]:
            # _analysis.jsonのファイルを対象とする（_jp_analysis.jsonは除外）
            if obj["Key"].endswith("_analysis.json") and not obj["Key"].endswith(
                "_jp_analysis.json"
            ):
                # 最終更新日が1週間以内のファイルを選択
                if obj["LastModified"].strftime("%Y-%m-%d") >= one_week_ago:
                    # 検索語が指定されている場合、ファイル名に検索語が含まれているかチェック
                    if search_term:
                        # ファイル名を検査
                        safe_term = (
                            search_term.lower()
                            .replace(" ", "_")
                            .replace("/", "_")
                            .replace("\\", "_")
                        )
                        if f"pubmed_{safe_term}_" in obj["Key"].lower():
                            analysis_files.append(obj["Key"])
                    else:
                        analysis_files.append(obj["Key"])

        return analysis_files

    except Exception as e:
        print(f"Error fetching files from S3: {str(e)}")
        return []


def chunk_articles(
    articles_data: List[Dict[str, Any]], max_tokens: int = 4000
) -> List[List[Dict[str, Any]]]:
    """論文データを適切なサイズのチャンクに分割"""
    chunks = []
    current_chunk = []
    current_tokens = 0

    # 基本プロンプトのトークン数を計算（空のデータで）
    base_prompt = create_weekly_analysis_prompt([])
    base_prompt_tokens = num_tokens_from_string(base_prompt)
    available_tokens = max_tokens - base_prompt_tokens

    for article in articles_data:
        # 論文データをJSON文字列に変換してトークン数を計算
        article_text = json.dumps(article, ensure_ascii=False)
        article_tokens = num_tokens_from_string(article_text)

        # チャンクのトークン数が制限を超える場合、新しいチャンクを開始
        if current_tokens + article_tokens > available_tokens and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0

        current_chunk.append(article)
        current_tokens += article_tokens

    # 最後のチャンクを追加
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def analyze_weekly_important_articles(
    articles_data: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    GPT APIを使用して、週次の重要論文を抽出・分析
    """
    # 論文を複数のチャンクに分割
    article_chunks = chunk_articles(articles_data)
    print(f"Split {len(articles_data)} articles into {len(article_chunks)} chunks")

    # 各チャンクから重要論文を抽出
    all_important_articles = []

    # 各チャンクを処理
    for i, chunk in enumerate(article_chunks):
        print(f"Processing chunk {i+1}/{len(article_chunks)} with {len(chunk)} articles")
        prompt = create_weekly_analysis_prompt(chunk)

        # トークン数を計算して表示
        prompt_tokens = num_tokens_from_string(prompt)
        print(f"Chunk {i+1} prompt tokens: {prompt_tokens}")

        try:
            # ChatGPT APIの呼び出し
            response = client.chat.completions.create(
                model=os.environ.get("GPT_MODEL", "gpt-4"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000,
            )

            # レスポンスのパース
            content = response.choices[0].message.content

            # JSONを抽出（余分なテキストがある場合の対策）
            json_match = re.search(r"(\[[\s\S]*\])", content)
            if json_match:
                content = json_match.group(1)

            chunk_results = json.loads(content)
            if isinstance(chunk_results, list):
                all_important_articles.extend(chunk_results)

        except Exception as e:
            print(f"Error processing chunk {i+1}: {str(e)}")
            continue

    # 全チャンクの結果から最も重要な論文を選定（最大10件）
    if all_important_articles:
        # 重要度スコアでソート（週次レポートとしての価値を評価）
        final_prompt = create_final_selection_prompt(all_important_articles)

        try:
            response = client.chat.completions.create(
                model=os.environ.get("GPT_MODEL", "gpt-4"),
                messages=[{"role": "user", "content": final_prompt}],
                temperature=0.1,
                max_tokens=3000,
            )

            content = response.choices[0].message.content
            json_match = re.search(r"(\[[\s\S]*\])", content)
            if json_match:
                content = json_match.group(1)

            final_selection = json.loads(content)
            return final_selection[:10]  # 最大10件に制限

        except Exception as e:
            print(f"Error in final selection: {str(e)}")
            # エラーの場合は最初の10件を返す
            return all_important_articles[:10]

    return []


def create_weekly_analysis_prompt(articles_data: List[Dict[str, Any]]) -> str:
    """
    週次重要論文分析用のプロンプトを生成
    """
    articles_json = json.dumps(articles_data, ensure_ascii=False)

    return f"""
あなたは医学研究の専門家です。提供された論文データから、今週の最も重要な論文を選定し、週次レポートを作成してください。

## 分析対象の論文データ
{articles_json}

## 選定基準
1. 以下の観点から論文の重要性を評価してください：
   - 臨床実践への影響度（即座に実践に影響を与える可能性）
   - 科学的新規性（新しい発見、概念、メカニズムの解明）
   - インパクトファクターとジャーナルの評価
   - 研究デザインの質（RCT、大規模コホート研究、高品質メタ分析を重視）
   - 医療現場での議論を呼ぶ可能性
   - ガイドライン改訂につながる可能性

2. 各論文について以下を評価・記載してください：
   - なぜこの論文が今週の重要論文として選定されたか
   - 主要な発見と結論の要約
   - 臨床実践への具体的な影響
   - 今後の研究や実践への示唆
   - 議論すべきポイントや限界

3. 論文間の関連性がある場合は、それも指摘してください。

以下のJSON形式で返答してください（最も重要な論文から順に）:
[
  {{
    "pmid": "論文のPMID",
    "journal": "ジャーナル名",
    "publication_year": "出版年",
    "title": "論文のタイトル",
    "weekly_importance_reason": "今週の重要論文として選定した理由",
    "key_findings": "主要な発見（箇条書きで3-5点）",
    "clinical_impact": "臨床実践への影響",
    "future_implications": "今後の研究・実践への示唆",
    "discussion_points": "議論すべきポイント",
    "related_articles": ["関連する他の論文のPMID（もしあれば）"]
  }}
]

重要性の高い論文のみを選定してください。品質重視で、無理に数を増やす必要はありません。
"""


def create_final_selection_prompt(articles_data: List[Dict[str, Any]]) -> str:
    """
    最終選定用のプロンプトを生成
    """
    articles_json = json.dumps(articles_data, ensure_ascii=False)

    return f"""
あなたは医学研究の専門家です。以下の論文リストから、今週の週次レポートに含めるべき最も重要な論文を最大10件選定してください。

## 候補論文
{articles_json}

## 最終選定基準
1. 週次レポートとしての価値を最優先に考慮
2. 読者（医療従事者）にとっての実用性と関心度
3. トピックの多様性（同じような内容の論文は最も重要な1つに絞る）
4. 最新の医療トレンドとの関連性
5. エビデンスレベルと研究の質

選定した論文を重要度順に並べ、元のデータ構造を保持したまま返してください。
必要に応じて、weekly_importance_reasonを更新して、なぜこの論文が週次レポートに含まれるべきかを明確にしてください。

JSON形式で、選定した論文のリストを返してください。
"""


def lambda_handler(event, context):
    try:
        print(f"Weekly analysis started at {datetime.now().isoformat()}")

        # バケット名を取得
        bucket_name = os.environ.get("BUCKET_NAME")
        if not bucket_name:
            raise ValueError("BUCKET_NAME environment variable is not set")

        # イベントから検索語を取得（指定されていない場合はNone）
        search_term = None
        if event and isinstance(event, dict) and "search_term" in event:
            search_term = event["search_term"]
            print(f"Using search term from event: {search_term}")

        # 過去1週間の解析済みファイルを取得（検索語に基づいてフィルタリング）
        analysis_files = get_files_from_last_week(bucket_name, search_term)
        print(
            f"Found {len(analysis_files)} analysis files from last week for term: {search_term or 'all terms'}"
        )

        if not analysis_files:
            print("No files to process. Exiting.")
            return {"statusCode": 200, "message": "No files to process"}

        # 全ての論文データを取得
        all_articles = []
        for file_key in analysis_files:
            try:
                response = s3.get_object(Bucket=bucket_name, Key=file_key)
                file_data = json.loads(response["Body"].read().decode("utf-8"))

                # impactful_articles配列から論文データを取得
                if "impactful_articles" in file_data:
                    # 元ファイル情報を追加
                    for article in file_data["impactful_articles"]:
                        article["source_file"] = file_key
                        article["analysis_date"] = file_data.get("metadata", {}).get(
                            "analysis_date", ""
                        )
                    all_articles.extend(file_data["impactful_articles"])
            except Exception as e:
                print(f"Error processing file {file_key}: {str(e)}")
                continue

        print(f"Total articles to analyze: {len(all_articles)}")

        if not all_articles:
            print("No articles found in the analysis files. Exiting.")
            return {"statusCode": 200, "message": "No articles found"}

        # 週次の重要論文を分析・選定
        weekly_important_articles = analyze_weekly_important_articles(all_articles)

        if not weekly_important_articles:
            print("No important articles selected for weekly report. Exiting.")
            return {"statusCode": 200, "message": "No important articles selected"}

        # 出力JSONの作成
        output_json = {
            "metadata": {
                "generated_date": datetime.now().isoformat(),
                "period_start": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
                "period_end": datetime.now().strftime("%Y-%m-%d"),
                "search_term": search_term or "all",
                "files_analyzed": len(analysis_files),
                "total_articles_reviewed": len(all_articles),
                "articles_selected": len(weekly_important_articles),
                "report_type": "weekly_important_articles",
            },
            "weekly_highlights": {
                "summary": f"今週は{len(all_articles)}件の論文から{len(weekly_important_articles)}件の重要論文を選定しました。",
                "top_journals": list(
                    set([article.get("journal", "") for article in weekly_important_articles])
                ),
                "key_topics": [],  # GPTの分析結果から抽出することも可能
            },
            "important_articles": weekly_important_articles,
        }

        # 結果をS3に保存（検索語をファイル名に含める）
        date_str = datetime.now().strftime("%Y%m%d")
        # ファイル名に使用できる形式に検索語を変換
        safe_term = ""
        if search_term:
            safe_term = search_term.lower().replace(" ", "_").replace("/", "_").replace("\\", "_")
            output_key = f"weekly_analysis_{safe_term}_{date_str}.json"
        else:
            output_key = f"weekly_analysis_{date_str}.json"

        s3.put_object(
            Bucket=bucket_name,
            Key=output_key,
            Body=json.dumps(output_json, ensure_ascii=False, indent=2),
            ContentType="application/json",
        )

        print(f"Weekly analysis report saved to s3://{bucket_name}/{output_key}")

        return {
            "statusCode": 200,
            "message": "Weekly analysis completed successfully",
            "search_term": search_term or "all",
            "output_file": output_key,
            "articles_selected": len(weekly_important_articles),
        }

    except Exception as e:
        print(f"Error in weekly analysis: {str(e)}")
        return {
            "statusCode": 500,
            "error": "Error processing request",
            "details": str(e),
        }
