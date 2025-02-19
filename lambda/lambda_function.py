import json
import boto3
import os
import datetime
import requests
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

# S3クライアント作成
s3 = boto3.client('s3')

def fetch_article_data(pmid_list: List[str]) -> Dict:
    """
    EFetchを使用して論文の詳細情報とアブストラクトを取得
    """
    efetch_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        "?db=pubmed"
        f"&id={','.join(pmid_list)}"
        "&rettype=abstract"
        "&retmode=xml"
    )

    print(f"Fetching detailed data from EFetch API: {efetch_url}")
    response = requests.get(efetch_url)
    response.raise_for_status()

    root = ET.fromstring(response.text)
    articles_data = {}

    for article in root.findall("./PubmedArticle"):
        try:
            # 基本情報の取得
            pmid = article.findtext("./MedlineCitation/PMID")
            if not pmid:
                continue

            # タイトルの取得
            title = article.findtext("./MedlineCitation/Article/ArticleTitle", "")

            # アブストラクトの取得（複数段落対応）
            abstract_elems = article.findall(".//AbstractText")
            abstract_texts = []

            for elem in abstract_elems:
                # ラベルがある場合は追加
                label = elem.get('Label', elem.get('NlmCategory', ''))
                text = elem.text
                if text:
                    if label:
                        abstract_texts.append(f"{label}: {text.strip()}")
                    else:
                        abstract_texts.append(text.strip())

            full_abstract = "\n".join(abstract_texts)

            # 著者情報の取得
            authors = []
            author_list = article.findall(".//Author")
            for author in author_list:
                last_name = author.findtext("LastName", "")
                fore_name = author.findtext("ForeName", "")
                if last_name or fore_name:
                    authors.append(f"{last_name} {fore_name}".strip())

            # ジャーナル情報の取得
            journal = article.findtext(".//Journal/Title", "")
            pub_date = article.findtext(".//PubDate/Year", "")

            # データの格納
            articles_data[pmid] = {
                "pmid": pmid,
                "title": title,
                "abstract": full_abstract,
                "authors": authors,
                "journal": journal,
                "publication_year": pub_date,
                "fetch_date": datetime.datetime.now().isoformat()
            }

        except Exception as e:
            print(f"Error processing article {pmid}: {str(e)}")
            continue

    return articles_data

def lambda_handler(event, context):
    try:
        # 環境変数から設定を取得
        search_term = os.environ.get('SEARCH_TERM', 'sepsis')
        bucket_name = os.environ.get('BUCKET_NAME', 'my-pubmed-bucket')

        # 前日の日付を取得
        yesterday = datetime.date.today() - datetime.timedelta(days=1)

        # ESearch APIのURL作成
        esearch_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            "?db=pubmed"
            f"&term={search_term}"
            "&retmode=json"
            "&retmax=1000"
            f"&datetype=edat"
            f"&mindate={yesterday.strftime('%Y/%m/%d')}"
            f"&maxdate={datetime.date.today().strftime('%Y/%m/%d')}"
        )

        print(f"Searching PubMed with URL: {esearch_url}")

        # ESearch APIリクエスト
        response = requests.get(esearch_url)
        response.raise_for_status()
        data = response.json()
        pmid_list = data.get("esearchresult", {}).get("idlist", [])

        print(f"Found {len(pmid_list)} articles.")

        if not pmid_list:
            return {
                "statusCode": 200,
                "body": f"No new articles found for {search_term}."
            }

        # 詳細情報とアブストラクトの取得
        articles_data = fetch_article_data(pmid_list)

        # ファイル名作成（タイムスタンプ付き）
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"pubmed_{search_term}_{timestamp}.json"

        # メタデータの追加
        output_data = {
            "metadata": {
                "search_term": search_term,
                "search_date": datetime.datetime.now().isoformat(),
                "total_articles": len(articles_data),
                "date_range": {
                    "from": yesterday.isoformat(),
                    "to": datetime.date.today().isoformat()
                }
            },
            "articles": articles_data
        }

        # S3にアップロード
        s3.put_object(
            Bucket=bucket_name,
            Key=file_name,
            Body=json.dumps(output_data, ensure_ascii=False, indent=2),
            ContentType="application/json"
        )

        print(f"Uploaded file to s3://{bucket_name}/{file_name}")

        return {
            "statusCode": 200,
            "body": f"Successfully stored {len(articles_data)} articles with abstracts to {file_name} in {bucket_name}."
        }

    except requests.exceptions.RequestException as e:
        print(f"Error making HTTP request: {str(e)}")
        return {
            "statusCode": 500,
            "body": f"Error fetching data from PubMed API: {str(e)}"
        }
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return {
            "statusCode": 500,
            "body": f"Unexpected error occurred: {str(e)}"
        }
