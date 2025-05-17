# PubMed 医学研究パイプライン

![AWS](https://img.shields.io/badge/AWS-CDK-orange)
![Python](https://img.shields.io/badge/Python-3.11-blue)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-green)

PubMed APIを使用して敗血症（sepsis）および急性呼吸窮迫症候群（ARDS）に関連する最新の学術論文を自動取得し、OpenAI GPTモデルによる分析、エビデンス抽出、日本語翻訳までを行うサーバーレスパイプラインです。AWSのサービスを活用し、完全自動化された医学文献処理システムを提供します。

## 📋 特徴

- **複数疾患の論文収集**: PubMedからsepsisとARDSの論文を独立して自動取得
- **疾患別データ管理**: 各疾患の論文を個別に管理し、検索から分析まで別々のパイプラインで処理
- **自動論文収集**: PubMedから最新論文を毎日自動取得
- **AI分析**: OpenAI GPTを使用した論文の重要度評価と要約
- **日本語翻訳**: 分析結果の自動日本語翻訳
- **エビデンス抽出**: 指定された臨床的クエスチョン（CQ）に関連するエビデンスを週次で抽出
- **AWSサーバーレス**: EventBridge、Lambda、S3、Step Functionsによる堅牢な構成

## 🏗️ アーキテクチャ

```
┌───────────────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  EventBridge          │───>│  Fetch      │───>│    S3       │───>│  Step       │
│  (sepsis/ARDS毎日実行)│    │  Lambda     │    │  Bucket     │    │  Functions  │
└───────────────────────┘    └─────────────┘    └─────────────┘    └──────┬──────┘
                                                                           │
                                                     ┌─────────────────────┼─────────────────┐
                                                     │                     │                 │
                                               ┌─────▼─────┐         ┌─────▼─────┐     ┌─────▼─────┐
                                               │  分析     │         │  翻訳     │     │  成功/失敗 │
                                               │  Lambda   │────────>│  Lambda   │────>│  状態     │
                                               └───────────┘         └───────────┘     └───────────┘

┌─────────────────────────┐
│ EventBridge             │
│ (sepsis/ARDS週次実行)   │
└─────────┬───────────────┘
          │
          ▼
┌─────────────┐           ┌─────────────┐
│  週次エビデンス│           │             │
│  抽出Lambda   │─────────▶│    S3       │
└─────────────┘           │  Bucket     │
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

### 1. 複数疾患の論文取得機能 (`lambda_function.py`)
- PubMed APIを使用して敗血症およびARDS関連の最新論文を独立して検索
- 前日分の論文を自動取得
- 疾患名をファイル名に含め、各疾患のデータを個別に管理
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
- 各疾患に対して個別に週次エビデンス抽出を実行
- 疾患別のファイル名で結果を保存
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
cd pubmed-medical-pipeline
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
- `OPENAI_API_KEY`: OpenAI APIキー
- `GPT_MODEL`: 使用するGPTモデル（デフォルト: "gpt-4"）
- `CDK_DEFAULT_REGION`: AWS リージョン（デフォルト: "ap-northeast-1"）

注: 検索対象のキーワードはCDKスタックで定義されるため、環境変数での設定は不要になりました。

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
   - EventBridgeによって毎日起動
     - sepsis: UTC 0:05（JST 9:05）
     - ARDS: UTC 0:15（JST 9:15）
   - PubMed APIから前日の対象疾患関連論文を検索・取得
   - 取得データをJSON形式でS3に保存（疾患名をファイル名に含む）
   - S3へのファイル保存をトリガーにStep Functionsワークフローが開始
   - 分析Lambdaが重要論文を抽出・分析
   - 翻訳Lambdaが分析結果を日本語に翻訳
   - すべての処理結果がS3に保存

2. **エビデンス抽出フロー（毎週月曜実行）**:
   - EventBridgeによって毎週月曜日に起動
     - sepsis: UTC 1:00（JST 10:00）
     - ARDS: UTC 1:15（JST 10:15）
   - 過去1週間分の分析済み論文から対象疾患に関連するエビデンスを抽出
   - エビデンスレポートがS3に保存（疾患名をファイル名に含む、関連論文がある場合のみ）

## 📊 出力ファイル形式

### 1. 論文取得結果
```
pubmed_sepsis_YYYYMMDD.json
pubmed_ards_YYYYMMDD.json
```

```json
{
  "metadata": {
    "search_term": "sepsis", // または "ards"
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

### 2. 分析結果
```
pubmed_sepsis_YYYYMMDD_analysis.json
pubmed_ards_YYYYMMDD_analysis.json
```

```json
{
  "metadata": {
    "original_file": "s3://my-pubmed-bucket/pubmed_sepsis_20250319.json",
    "analysis_date": "2025-03-19T00:10:00Z",
    "search_term": "sepsis", // または "ards"
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

### 3. 日本語翻訳結果
```
pubmed_sepsis_YYYYMMDD_jp_analysis.json
pubmed_ards_YYYYMMDD_jp_analysis.json
```

```json
{
  "metadata": {
    "original_file": "s3://my-pubmed-bucket/pubmed_sepsis_20250319.json",
    "analysis_date": "2025-03-19T00:10:00Z",
    "translation_date": "2025-03-19T00:15:00Z",
    "search_term": "sepsis", // または "ards"
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

### 4. 週次エビデンス抽出結果
```
weekly_evidence_sepsis_YYYYMMDD.json
weekly_evidence_ards_YYYYMMDD.json
```

```json
{
  "metadata": {
    "search_term": "sepsis", // または "ards"
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

4. **GitHubの.gitignore反映問題**
   - 既にコミットされたファイルを.gitignoreに追加した場合:
     ```bash
     git rm -r --cached .
     git add .
     git commit -m "Apply new .gitignore rules"
     git push
     ```

## 📝 カスタマイズ

### 新たな疾患の追加
`pubmed_search_stack.py`に新しい疾患用のEventBridgeルールを追加：

```python
# 新疾患用のEventBridgeルール
new_disease_rule = events.Rule(
    self,
    "DailyNewDiseaseSearchRule",
    schedule=events.Schedule.cron(
        minute="25",  # 時間をずらす
        hour="0",  # UTC 0:25
    ),
)

# 新疾患用のルールにLambda関数をターゲットとして追加
new_disease_rule.add_target(targets.LambdaFunction(
    fetch_lambda,
    event=events.RuleTargetInput.from_object({"search_term": "new_disease_name"})
))
```

### 対象CQの追加/変更
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