# 週次重要論文分析機能 - 実装ガイド

## 実装概要

PubMed論文検索・分析パイプラインに、週次で重要論文を選定・分析する機能を追加します。

## 追加機能の詳細

1. **週次重要論文分析**:
   - 毎週月曜日の10時に実行
   - 過去1週間分の分析済み論文から最も重要な論文を選定
   - 臨床実践への影響度、科学的新規性、研究の質などを総合的に評価
   - 結果をJSON形式で保存（最大10件の重要論文）

2. **評価基準**:
   - 臨床実践への即座の影響度
   - 科学的新規性と発見の重要性
   - ジャーナルのインパクトファクター
   - 研究デザインの質（RCT、大規模研究を重視）
   - ガイドライン改訂の可能性
   - 医療現場での議論を呼ぶ可能性

## 実装手順

### 1. ディレクトリとファイルの作成

```bash
# Lambda関数用のディレクトリを作成
mkdir -p weekly_analyze_lambda
```

### 2. Lambda関数の実装

`weekly_analyze_lambda/weekly_analyze_function.py` ファイルを作成し、週次分析ロジックを実装します。

### 3. CDKスタックの更新

`pubmed_search/pubmed_search_stack.py` ファイルを更新し、週次分析用のLambda関数とEventBridgeルールを追加します。

### 4. デプロイ

```bash
# CDKのデプロイ
cdk deploy
```

## アーキテクチャ

```
┌─────────────┐
│ EventBridge │
│ (毎週月曜日) │
└─────┬───────┘
      │
      ▼
┌─────────────┐    ┌─────────────┐
│  週次分析    │    │             │
│  Lambda      │───▶│    S3       │
└─────────────┘    │  Bucket     │
                   └─────────────┘
```

## 出力ファイル形式

生成されるJSONファイルの構造:

```json
{
  "metadata": {
    "generated_date": "2025-03-24T01:00:00Z",
    "period_start": "2025-03-17",
    "period_end": "2025-03-24",
    "search_term": "sepsis",
    "files_analyzed": 7,
    "total_articles_reviewed": 21,
    "articles_selected": 8,
    "report_type": "weekly_important_articles"
  },
  "weekly_highlights": {
    "summary": "今週は21件の論文から8件の重要論文を選定しました。",
    "top_journals": ["NEJM", "Lancet", "JAMA"],
    "key_topics": []
  },
  "important_articles": [
    {
      "pmid": "12345678",
      "journal": "New England Journal of Medicine",
      "publication_year": "2025",
      "title": "論文タイトル",
      "weekly_importance_reason": "今週の重要論文として選定した理由",
      "key_findings": "主要な発見（箇条書きで3-5点）",
      "clinical_impact": "臨床実践への影響",
      "future_implications": "今後の研究・実践への示唆",
      "discussion_points": "議論すべきポイント",
      "related_articles": ["関連する他の論文のPMID"]
    }
  ]
}
```

## 注意点

1. 最大10件の重要論文を選定します。品質重視で、無理に数を増やしません。
2. Lambda関数のタイムアウトは300秒（5分）に設定されていますが、処理するファイル数が多い場合は増やす必要があるかもしれません。
3. 論文間の関連性も分析し、関連する論文がある場合はrelated_articlesフィールドに記載されます。
