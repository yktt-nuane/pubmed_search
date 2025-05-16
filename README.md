# PubMed 敗血症研究パイプライン

![AWS](https://img.shields.io/badge/AWS-CDK-orange)
![Python](https://img.shields.io/badge/Python-3.11-blue)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-green)

PubMed APIを使用して敗血症（sepsis）に関連する最新の学術論文を自動取得し、OpenAI GPTモデルによる分析、エビデンス抽出、日本語翻訳までを行うサーバーレスパイプラインです。AWSのサービスを活用し、完全自動化された論文処理システムを提供します。

## 📋 特徴

- **自動論文収集**: PubMedから敗血症関連の最新論文を毎日自動取得
- **AI分析**: OpenAI GPTを使用した論文の重要度評価と要約
- **日本語翻訳**: 分析結果の自動日本語翻訳
- **エビデンス抽出**: 指定された臨床的クエスチョン（CQ）に関連するエビデンスを週次で抽出
- **AWSサーバーレス**: EventBridge、Lambda、S3、Step Functionsによる堅牢な構成

## 🏗️ アーキテクチャ

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

┌─────────────┐
│ EventBridge │
│ (毎週月曜日) │
└─────┬───────┘
      │
      ▼
┌─────────────┐    ┌─────────────┐
│  週次エビデンス │    │             │
│  抽出Lambda   │───▶│    S3       │
└─────────────┘    │  Bucket     │
                   └─────────────┘
```

## 📁 ディレクトリ構造

```
project/
├── .env                     # 環境変数設定ファイル
├── app.py                   # CDKエントリーポイント
├── lambda/                  # 論文取得用Lambda
│   └── lambda_function.py   # PubMed APIからの論文取得機能
├── analyze_lambda/          # 論文分析用Lambda
│   └── analyze_function.py  # GPTによる論文分析機能
├── translate_lambda/        # 日本語翻訳用Lambda
│   └── translate_function.py# 分析結果の日本語翻訳
├── weekly_evidence_lambda/  # 週次エビデンス抽出用Lambda
│   └── weekly_evidence_function.py # CQに関するエビデンス抽出
├── layers/                  # Lambda Layers
│   └── openai/              # OpenAI APIクライアント用レイヤー
├── pubmed_search/           # CDKスタック定義
│   └── pubmed_search_stack.py # インフラ構成定義
├── tests/                   # テストコード
│   └── unit/               
│       └── test_pubmed_search_stack.py
├── create-layer.sh          # OpenAIレイヤー作成スクリプト
└── README.md
```

## 💡 主要機能の詳細

### 1. 論文取得機能 (`lambda_function.py`)
- PubMed APIを使用して敗血症関連の最新論文を検索
- 前日分の論文を自動取得
- 論文のメタデータとアブストラクトを保存

### 2. 論文分析機能 (`analyze_function.py`)
- 高インパクトジャーナルの論文を優先して選定
- 各論文の重要性、要約、臨床的含意を分析
- 最も重要な論文（最大3件）を選定

### 3. 日本語翻訳機能 (`translate_function.py`)
- 分析結果を専門的な日本語に翻訳
- 医学用語の適切な翻訳を実施
- 元の英語表現も括弧内に保持

### 4. 週次エビデンス抽出機能 (`weekly_evidence_function.py`)
- 4つの敗血症関連CQに関するエビデンスを抽出
  - CQ4-1: 敗血症に対する PMX-DHP
  - CQ4-2: 敗血症性AKIに対する早期腎代替療法
  - CQ4-3: 敗血症性AKIに対する持続的腎代替療法
  - CQ4-4: 敗血症性AKIにおける血液浄化量の増加
- 毎週月曜日に過去1週間分の論文からエビデンスを抽出
- エビデンスの価値評価を含む詳細なレポートを生成

## 🚀 セットアップ方法

### 前提条件
- AWS CLIがインストール済みであること
- AWS CDKがインストール済みであること
- Python 3.11以上がインストール済みであること
- Dockerがインストール済みであること（レイヤー作成用）

### 1. リポジトリをクローン
```bash
git clone <repository-url>
cd pubmed-sepsis-pipeline
```

### 2. 仮想環境の作成と依存関係のインストール
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate.bat
pip install -r requirements.txt
pip install -r requirements-dev.txt  # 開発用依存関係（テスト等）
```

### 3. 環境変数の設定
`.env.sample`を`.env`にコピーして必要な値を設定します：

```bash
cp .env.sample .env
# エディタで.envを開いて編集
```

必須環境変数：
- `BUCKET_NAME`: S3バケット名（グローバルで一意）
- `SEARCH_TERM`: PubMedで検索するキーワード（デフォルト: "sepsis"）
- `OPENAI_API_KEY`: OpenAI APIキー
- `GPT_MODEL`: 使用するGPTモデル（デフォルト: "gpt-4"）
- `CDK_DEFAULT_REGION`: AWS リージョン（デフォルト: "ap-northeast-1"）

### 4. OpenAIレイヤーの作成
```bash
chmod +x create-layer.sh
./create-layer.sh
```

### 5. CDKのブートストラップとデプロイ
```bash
cdk bootstrap
cdk deploy
```

## 🔄 処理フロー

1. **論文取得フロー（毎日実行）**:
   - EventBridgeによって毎日0:05 UTC（JST 9:05）に論文取得Lambdaが起動
   - PubMed APIから前日の敗血症関連論文を検索・取得
   - 取得データをJSON形式でS3に保存
   - S3へのファイル保存をトリガーにStep Functionsワークフローが開始
   - 分析Lambdaが重要論文を抽出・分析
   - 翻訳Lambdaが分析結果を日本語に翻訳
   - すべての処理結果がS3に保存

2. **エビデンス抽出フロー（毎週月曜実行）**:
   - EventBridgeによって毎週月曜日1:00 UTC（JST 10:00）にエビデンス抽出Lambdaが起動
   - 過去1週間分の分析済み論文から4つのCQに関連するエビデンスを抽出
   - エビデンスレポートがS3に保存（関連論文がある場合のみ）

## 📊 出力ファイル形式

### 1. 論文取得結果 (`pubmed_sepsis_YYYYMMDD.json`)
```json
{
  "metadata": {
    "search_term": "sepsis",
    "search_date": "2025-03-19T00:05:00Z",
    "total_articles": 15,
    "date_range": {
      "from": "2025-03-18",
      "to": "2025-03-19"
    }
  },
  "articles": {
    "12345678": {
      "pmid": "12345678",
      "title": "論文タイトル",
      "abstract": "アブストラクト全文...",
      "authors": ["著者1", "著者2"],
      "journal": "ジャーナル名",
      "publication_year": "2025",
      "fetch_date": "2025-03-19T00:05:30Z"
    },
    // ... 他の論文
  }
}
```

### 2. 分析結果 (`pubmed_sepsis_YYYYMMDD_analysis.json`)
```json
{
  "metadata": {
    "original_file": "s3://my-pubmed-bucket/pubmed_sepsis_20250319.json",
    "analysis_date": "2025-03-19T00:10:00Z",
    "search_term": "sepsis",
    "total_analyzed": 15,
    "total_selected": 3
  },
  "impactful_articles": [
    {
      "pmid": "12345678",
      "journal": "New England Journal of Medicine",
      "publication_year": "2025",
      "impact_reason": "高インパクトジャーナルでの無作為化比較試験...",
      "summary": "この研究では...",
      "implications": "この結果は臨床実践に重要な示唆を与える..."
    },
    // ... 他の重要論文（最大3件）
  ]
}
```

### 3. 日本語翻訳結果 (`pubmed_sepsis_YYYYMMDD_jp_analysis.json`)
```json
{
  "metadata": {
    "original_file": "s3://my-pubmed-bucket/pubmed_sepsis_20250319.json",
    "analysis_date": "2025-03-19T00:10:00Z",
    "translation_date": "2025-03-19T00:15:00Z",
    "search_term": "sepsis",
    "total_analyzed": 15,
    "total_selected": 3,
    "original_language": "en",
    "target_language": "ja"
  },
  "impactful_articles": [
    {
      "pmid": "12345678",
      "journal": "New England Journal of Medicine",
      "publication_year": "2025",
      "impact_reason": "高インパクトジャーナルでの無作為化比較試験...",
      "summary": "この研究では...",
      "implications": "この結果は臨床実践に重要な示唆を与える..."
    },
    // ... 他の重要論文（最大3件）
  ]
}
```

### 4. 週次エビデンス抽出結果 (`weekly_evidence_YYYYMMDD.json`)
```json
{
  "metadata": {
    "generated_date": "2025-03-24T01:00:00Z",
    "period_start": "2025-03-17",
    "period_end": "2025-03-24",
    "files_analyzed": 7,
    "articles_analyzed": 21
  },
  "evidence_articles": {
    "CQ4-1": [
      {
        "pmid": "12345678",
        "journal": "Critical Care Medicine",
        "publication_year": "2025",
        "title": "論文タイトル",
        "summary": "論文の簡潔な要約",
        "evidence_value": "この論文がCQに対するエビデンスとしての価値についての説明"
      }
    ],
    "CQ4-2": [],
    "CQ4-3": [...],
    "CQ4-4": [...]
  }
}
```

## 🧪 テスト

### ユニットテスト実行
```bash
pytest tests/
```

### CDKスタックテスト
```bash
cdk synth  # CloudFormationテンプレートの生成
```

## 🔧 トラブルシューティング

### よくある問題と解決策

1. **デプロイエラー**
   - バケット名が既に使用されている場合は、`.env`ファイルで一意のバケット名を指定してください
   - AWS認証情報が適切に設定されていることを確認: `aws configure`

2. **Lambda実行エラー**
   - CloudWatchログでエラー内容を確認
   - OpenAI APIキーが正しく設定されていることを確認
   - Lambda関数のタイムアウト設定を確認（デフォルト: 300秒）

3. **OpenAIレイヤー作成エラー**
   - Dockerが稼働していることを確認
   - 十分なディスク容量があることを確認

## 📝 カスタマイズ

### 検索キーワードの変更
`.env`ファイルの`SEARCH_TERM`値を変更して再デプロイ：
```
SEARCH_TERM=septic shock
```

### 分析対象CQの追加/変更
`weekly_evidence_lambda/weekly_evidence_function.py`内の`CQ_LIST`配列を編集して再デプロイ：
```python
CQ_LIST = [
    {
        "id": "新しいCQ-ID",
        "question": "新しい臨床的質問",
        "keywords": ["キーワード1", "キーワード2"]
    },
    # ... 他のCQ
]
```

## 📄 ライセンス

このプロジェクトはMITライセンスの下で公開されています。

## 🤝 貢献

バグ報告や機能リクエストは、プロジェクトのIssueトラッカーに提出してください。プルリクエストも歓迎します。

---

開発・運用に関するご質問は、プロジェクト管理者までお問い合わせください。