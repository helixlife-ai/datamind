# DataMind

![DataMind Logo](docs/images/logo.png)

## Intelligent Document Processing & Semantic Search Engine

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org)
[![Version](https://img.shields.io/badge/version-0.2.1-green.svg)](https://github.com/helixlife-ai/datamind/releases)

[English](README.md) | [中文](docs/README_zh.md)

## 📖 Introduction

DataMind is a powerful intelligent data processing and semantic search system. It automatically processes documents in various formats, converts unstructured data into structured representations using advanced vectorization techniques, and provides efficient hybrid search functionality.

### 🎯 Key Applications

- Enterprise Document Management
- Knowledge Base Semantic Search
- Data Asset Unified Management
- Intelligent Document Analysis
- Incremental Data Updates

## ✨ Core Features

### 🔄 Intelligent Document Processing
- **Multi-format Support**: Handles JSON, CSV, Excel, XML, TXT, Markdown, etc.
- **Smart Parsing**: Auto-detects file encoding and type, extracts document structure
- **Vector Processing**: Multi-language text vectorization based on Sentence-Transformers
- **Unified Storage**: Efficient storage of structured data and vector representations using DuckDB
- **Incremental Updates**: Supports incremental document processing for improved efficiency

### 🔍 Hybrid Search Engine
- **Semantic Search**: High-performance vector similarity search based on FAISS
- **Structured Queries**: Supports exact matching and condition filtering
- **Hybrid Ranking**: Intelligent fusion of vector similarity and structured query results
- **Aggregation Analysis**: Supports multi-dimensional data analysis and visualization
- **Smart Caching**: File processing cache mechanism for improved retrieval performance

### 🎨 New Features (v0.2.1)
- **Model Management**: Unified model management system, supports both local and API calls
- **Environment Config**: Optimized environment variable configuration for improved security
- **Async Support**: Enhanced asynchronous API call support
- **Error Handling**: Improved error handling and logging
- **Search Enhancement**: 
  * Intelligent content deduplication and similarity analysis
  * Deep insights and relationship discovery
  * Multi-format result export
  * Timeline analysis
  * Improved result summarization

## 🚀 Quick Start

### Installation

```bash
# Clone the project
git clone https://github.com/helixlife-ai/datamind.git
cd datamind

# Install dependencies
pip install -r requirements.txt

# Generate test data
python scripts/generate_test_data.py
```

### Test Data Description

Generated test data includes AI-related documents in various formats:
- `ai_guide.md`: AI basics introduction
- `ai_models.json`: Mainstream AI model information
- `ml_algorithms.csv`: Machine learning algorithm comparison
- `ai_applications.xml`: AI application domain data
- `ai_companies.xlsx`: AI company information

### Usage Example

```python
# Set environment variables
import os
os.environ["DEEPSEEK_API_KEY"] = "your_api_key"
os.environ["DEEPSEEK_BASE_URL"] = "your_base_url"

from datamind import UnifiedSearchEngine, DataProcessor
from pathlib import Path

# Initialize components
processor = DataProcessor()
search_engine = UnifiedSearchEngine()

# Process data directory
input_dirs = ["work_dir/test_data"]  # Test data directory
stats = processor.process_directory(input_dirs)

# Execute search
# Search for machine learning related content
results = search_engine.search("machine learning algorithms and applications")
print(results)

# Supports various query types
results = search_engine.search("type:markdown")  # Search Markdown files
results = search_engine.search("company:OpenAI")  # Search specific company
results = search_engine.search("file:json")  # Search by file type
results = search_engine.search("modified:>2024-01-01")  # Search by date
```

### Intelligent Search Example
```python
from datamind import IntentParser, SearchPlanner, SearchPlanExecutor

# Initialize intelligent search components
intent_parser = IntentParser()
planner = SearchPlanner()
executor = SearchPlanExecutor(search_engine)

# Execute intelligent search
query = "Find recent technological advances in deep learning and large language models"
parsed_intent = intent_parser.parse_query(query)
results = executor.execute_plan(planner.build_search_plan(parsed_intent))

# Export results
csv_path = executor.save_results_to_csv(results, "search_results.csv")
print(f"Results saved to: {csv_path}")

# View statistics
print(f"Found {results['stats']['total']} relevant records")
print(f"Structured queries: {results['stats']['structured_count']}")
print(f"Vector queries: {results['stats']['vector_count']}")

# View key findings
for idx, concept in enumerate(results['insights']['key_concepts'][:3], 1):
    print(f"Finding {idx}: {concept}")
```

## ⚙️ Configuration

### Environment Variables

The project uses the following environment variables:

- `DEEPSEEK_API_KEY`: (Required) LLM API key
- `DEEPSEEK_BASE_URL`: (Optional) LLM API base URL, defaults to "https://api.deepseek.com"

You can set these variables by:

1. Creating a `.env` file:
   ```bash
   cp .env.example .env
   # Then edit .env with actual values
   ```

2. Or setting them directly:
   ```bash
   export DEEPSEEK_API_KEY=your-api-key-here
   export DEEPSEEK_BASE_URL=https://api.deepseek.com
   ```

## 📊 Performance Metrics

- Document Processing Speed: ~150 docs/sec (standard configuration)
- Vector Search Latency: <30ms (million-scale data)
- Document Scale Support: Million-level (16GB RAM)
- Vector Dimensions: 384 (using MiniLM model)
- Cache Hit Rate: >90% (normal usage)

## 🗺️ Roadmap

- [x] Incremental Update Support
- [x] File Caching Mechanism
- [ ] Web Interface Support
- [ ] REST API Interface
- [ ] Distributed Processing Support
- [ ] Real-time Processing Pipeline
- [ ] More File Format Support

## 🤝 Contributing

PRs and Issues welcome! See [Contributing Guide](CONTRIBUTING.md) for details.

## 📄 License

This project is under MIT License - see [LICENSE](LICENSE) file

## 👥 Team

- Author: [jszhang]
- Email: zhangjingsong@helixlife.cn
- Team: [HelixLife AI Research Institute](https://github.com/helixlife-ai)
- Team Homepage: https://github.com/helixlife-ai

## 🙏 Acknowledgments

Thanks to these open source projects:
- [Sentence-Transformers](https://github.com/UKPLab/sentence-transformers)
- [FAISS](https://github.com/facebookresearch/faiss)
- [DuckDB](https://github.com/duckdb/duckdb)

## 环境变量配置

项目使用以下环境变量：

- `DATAMIND_LLM_API_KEY`: (必需) LLM API密钥
- `DATAMIND_LLM_API_BASE`: (可选) LLM API基础URL，默认为 "https://api.deepseek.com"

你可以通过以下方式设置环境变量：

1. 创建 `.env` 文件：
   ```bash
   cp .env.example .env
   # 然后编辑 .env 文件填入实际的值
   ```

2. 或者直接在环境中设置：
   ```bash
   export DATAMIND_LLM_API_KEY=your-api-key-here
   export DATAMIND_LLM_API_BASE=https://api.deepseek.com
   ```

## 项目结构

```
datamind/
├── api/              # 对外接口层
├── core/             # 核心功能实现
├── config/           # 配置文件
├── models/           # 模型定义
├── services/         # 业务逻辑层
└── utils/            # 工具函数

data/                 # 数据文件存储
├── unified_storage.duckdb
└── file_cache.pkl

docs/                 # 文档
examples/             # 示例代码
├── example_usage.py
└── ...

tests/               # 测试文件
work_dir/            # 工作目录
scripts/             # 脚本文件
model_cache/         # 模型缓存
```
