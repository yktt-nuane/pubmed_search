#!/bin/bash

# プロジェクトのルートディレクトリであることを確認
if [ ! -f "requirements-layer.txt" ]; then
    echo "Error: requirements-layer.txt not found in current directory"
    exit 1
fi

echo "Creating OpenAI Lambda Layer..."

# レイヤーディレクトリのクリーンアップと作成
echo "Cleaning up layer directory..."
rm -rf layers/openai/python
mkdir -p layers/openai/python

# Dockerを使用してAmazon Linux 2互換の環境でビルド
echo "Installing dependencies using Docker..."
docker run --rm \
  -v "$(pwd)/layers/openai/python:/lambda" \
  -v "$(pwd)/requirements-layer.txt:/requirements-layer.txt" \
  public.ecr.aws/sam/build-python3.11:latest \
  /bin/bash -c "pip install --upgrade pip && \
                python -m pip install -r /requirements-layer.txt -t /lambda \
                --platform manylinux2014_x86_64 \
                --implementation cp \
                --only-binary=:all: \
                --python-version=3.11"

if [ $? -ne 0 ]; then
    echo "Error: Failed to install dependencies"
    exit 1
fi

# 不要なファイルの削除
echo "Cleaning up unnecessary files..."
cd layers/openai/python || exit
find . -type d -name "tests" -exec rm -rf {} +
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
find . -type f -name "*.pyo" -delete
find . -type d -name "*.dist-info" -exec rm -rf {} +
find . -type d -name "*.egg-info" -exec rm -rf {} +

# サイズの確認
echo "Layer size:"
du -sh .

# 圧縮サイズの確認
cd ../
echo "Creating zip file..."
zip -r openai-layer.zip python/
echo "Compressed size:"
du -sh openai-layer.zip
rm openai-layer.zip

echo "Layer creation completed successfully"
