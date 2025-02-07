# DataMind

<p align="center">
  <img src="docs/images/logo.png" alt="DataMind Logo" width="200"/>
  <br>
  <em>智能文档处理与语义搜索引擎</em>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.8+-blue.svg" alt="Python"></a>
  <a href="#"><img src="https://img.shields.io/badge/version-0.2.0-green.svg" alt="Version"></a>
</p>

## 📖 简介

DataMind 是一个强大的智能数据处理和语义搜索系统。它能自动处理多种格式的文档,通过先进的向量化技术将非结构化数据转换为结构化表示,并提供高效的混合搜索功能。

### 🎯 主要应用场景

- 企业文档智能管理
- 知识库语义检索
- 数据资产统一管理
- 智能文档分析
- 增量数据更新

## ✨ 核心特性

### 🔄 智能文档处理
- **多格式支持**: 自动处理 JSON、CSV、Excel、XML、TXT、Markdown 等格式
- **智能解析**: 自动识别文件编码和类型,提取文档结构
- **向量化处理**: 基于 Sentence-Transformers 的多语言文本向量化
- **统一存储**: 采用 DuckDB 高效存储结构化数据和向量表示
- **增量更新**: 支持文档增量处理,提高处理效率

### 🔍 混合搜索引擎
- **语义搜索**: 基于 FAISS 的高性能向量相似度检索
- **结构化查询**: 支持精确匹配和条件过滤
- **混合排序**: 智能融合向量相似度和结构化查询结果
- **聚合分析**: 支持多维度数据分析和可视化
- **智能缓存**: 文件处理缓存机制,提升检索性能

### 🎨 新增特性 (v0.2.0)
- **文件缓存**: 智能文件处理缓存,避免重复处理
- **增量更新**: 支持文档增量更新处理
- **批量处理**: 优化批量文件处理性能
- **智能解析**: 增强的文件类型识别和内容提取
- **统计分析**: 详细的处理统计和性能指标

### 🎨 新增特性 (v0.1.0)
- **基础搜索引擎**: 支持结构化查询和向量查询的混合搜索
- **搜索结果格式化**: 支持将搜索结果导出为CSV文件
- **详细日志记录**: 实现详细的日志记录

## 🛠️ 技术架构

- **存储层**: DuckDB
- **向量引擎**: FAISS + Sentence-Transformers
- **处理框架**: Pandas + NumPy
- **API接口**: FastAPI (计划中)
- **缓存系统**: 文件级缓存

## 🚀 快速开始

### 安装

```bash
# 克隆项目
git clone https://github.com/helixlife-ai/datamind.git
cd datamind

# 安装依赖
pip install -r requirements.txt
```

### 使用示例

1. 环境配置:
```bash
# 创建并配置 .env 文件
DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_BASE_URL=your_base_url
```

2. 基础使用:
```python
from datamind import UnifiedSearchEngine, DataProcessor
from pathlib import Path

# 初始化组件
processor = DataProcessor()
search_engine = UnifiedSearchEngine()

# 处理数据目录
input_dirs = ["source/test_data"]
stats = processor.process_directory(input_dirs)

# 执行搜索
results = search_engine.search("机器学习")
print(results)

# 支持多种查询方式
results = search_engine.search("file:json")  # 按文件类型搜索
results = search_engine.search("modified:>2024-01-01")  # 按时间搜索
```

3. 智能检索:
```python
from datamind import IntentParser, SearchPlanner, SearchPlanExecutor

# 设置DEEPSEEK的API密钥和基础URL
api_key = "<your_api_key> "
base_url = "<your_base_url>"

# 初始化智能检索组件
intent_parser = IntentParser(api_key=api_key, base_url=base_url)
planner = SearchPlanner()
executor = SearchPlanExecutor(search_engine)

# 执行智能检索
query = "找出上海2025年与人工智能专利技术相关的研究报告"
parsed_intent = intent_parser.parse_query(query)
results = executor.execute_plan(planner.build_search_plan(parsed_intent))

# 导出结果
csv_path = executor.save_results_to_csv(results, "search_results.csv")
```

## ⚙️ 配置说明

### 向量模型配置
```python
# 支持自定义向量模型
DEFAULT_MODEL = 'paraphrase-multilingual-MiniLM-L12-v2'
```

### 存储配置
```python
# 自定义数据库路径
DEFAULT_DB_PATH = "unified_storage.duckdb"
```

## 📊 性能指标

- 文档处理速度: ~150文档/秒
- 向量检索延迟: <30ms
- 支持文档规模: 百万级
- 向量维度: 384维
- 缓存命中率: >90%

## 🗺️ 开发路线

- [x] 增量更新支持
- [x] 文件缓存机制
- [ ] Web 界面支持
- [ ] REST API 接口
- [ ] 分布式处理支持
- [ ] 实时处理流水线
- [ ] 更多文件格式支持

## 🤝 参与贡献

欢迎提交 PR 或 Issue！详细信息请参考 [贡献指南](CONTRIBUTING.md)。

## 📄 开源协议

本项目采用 MIT 协议 - 详见 [LICENSE](LICENSE) 文件

## 👥 团队

- 作者: [jszhang]
- 邮箱: zhangjingsong@helixlife.cn
- 团队：[解螺旋AI研究院](https://github.com/helixlife-ai)
- 团队主页: https://github.com/helixlife-ai

## 🙏 致谢

感谢以下开源项目:
- [Sentence-Transformers](https://github.com/UKPLab/sentence-transformers)
- [FAISS](https://github.com/facebookresearch/faiss)
- [DuckDB](https://github.com/duckdb/duckdb)
