#!/bin/bash

# 新しいディレクトリを作成
mkdir -p translate_lambda
mkdir -p step_functions

# 翻訳Lambda関数ファイルを作成
touch translate_lambda/translate_function.py

# Step Functions定義ファイルを作成
touch step_functions/pubmed_workflow.json

# 既存のディレクトリ構造確認
echo "ディレクトリ構造を確認しています..."
find . -type d | sort

echo "セットアップ完了！"
