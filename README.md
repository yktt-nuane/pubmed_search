# PubMed 文献検索・分析・翻訳パイプライン

このプロジェクトは、PubMedから特定のキーワードに関連する最新の論文を自動取得し、OpenAI GPTを使用して英語で分析した後、日本語に翻訳するAWSサーバーレスパイプラインを構築します。

## 機能

- PubMedから毎日新しい論文を自動検索・取得
- 取得した論文をOpenAI GPTを使用して分析
- 分析結果を日本語に翻訳
- S3への結果保存
- Step Functionsによるワークフロー管理

## アーキテクチャ

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  EventBridge │───>│  Fetch      │───>│    S3       │───>│  Step       │
│  (毎日実行)  │    │  Lambda     │    │  Bucket     │    │  Functions  │
└─────────────┘    └─────────────┘    └─────────────┘    └──────┬──────┘
                                                                 │
                                               ┌─────────────────┼─────────────────┐
                                               │                 │                 │
                                         ┌─────▼─────┐     ┌─────▼─────┐     ┌─────▼─────┐
                                         │  分析     │     │  翻訳     │     │  成功/失敗 │
                                         │  Lambda   │────>│  Lambda   │────>│  状態     │
                                         └───────────┘     └───────────┘     └───────────┘
```

## ディレクトリ構造

```
project/
├── .env                  # 環境変数設定ファイル
├── app.py                # CDKエントリーポイント
├── lambda/               # 論文取得用Lambda
│   └── lambda_function.py
├── analyze_lambda/       # 論文分析用Lambda
│   └── analyze_function.py
├── translate_lambda/     # 日本語翻訳用Lambda
│   └── translate_function.py
├── layers/               # Lambda Layers
│   └── openai/           # OpenAI APIクライアント用レイヤー
├── step_functions/       # Step Functions定義
│   └── pubmed_workflow.json
├── pubmed_search/        # CDKスタック定義
│   └── pubmed_search_stack.py
└── README.md
```

## セットアップ方法

1. リポジトリをクローン
2. 必要な依存関係をインストール:
   ```
   pip install -r requirements.txt
   ```
3. `.env.sample`を`.env`にコピーして必要な値を設定
4. CDKのブートストラップを実行（初回のみ）:
   ```
   cdk bootstrap
   ```
5. デプロイ:
   ```
   cdk deploy
   ```

## 環境変数

`.env`ファイルに以下の環境変数を設定してください:

- `BUCKET_NAME`: S3バケット名（グローバルで一意）
- `SEARCH_TERM`: PubMedで検索するキーワード（デフォルト: "sepsis"）
- `OPENAI_API_KEY`: OpenAI APIキー
- `GPT_MODEL`: 使用するGPTモデル（デフォルト: "gpt-4"）
- `CDK_DEFAULT_REGION`: AWS リージョン（デフォルト: "ap-northeast-1"）

## 仕組み

1. EventBridgeによって毎日定刻に論文取得Lambdaが起動
2. 論文取得LambdaがPubMed APIから最新論文データを取得しS3に保存
3. S3へのファイル保存をトリガーにStep Functionsワークフローが開始
4. Step Functionsが分析Lambdaを実行し、論文を分析
5. 続いて翻訳Lambdaが実行され、分析結果を日本語に翻訳
6. 全てのファイルがS3バケットに保存される
