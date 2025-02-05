# DataMind

<p align="center">
  <img src="docs/images/logo.png" alt="DataMind Logo" width="200"/>
  <br>
  <em>智能文档处理与语义搜索引擎</em>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.8+-blue.svg" alt="Python"></a>
  <a href="#"><img src="https://img.shields.io/badge/version-0.1.0-green.svg" alt="Version"></a>
</p>

## 📖 简介

DataMind 是一个强大的智能数据处理和语义搜索系统。它能自动处理多种格式的文档,通过先进的向量化技术将非结构化数据转换为结构化表示,并提供高效的混合搜索功能。

### 🎯 主要应用场景

- 企业文档智能管理
- 知识库语义检索
- 数据资产统一管理
- 智能文档分析

## ✨ 核心特性

### 🔄 智能文档处理
- **多格式支持**: 自动处理 JSON、CSV、Excel、XML、TXT、Markdown 等格式
- **智能解析**: 自动识别文件编码和类型,提取文档结构
- **向量化处理**: 基于 Sentence-Transformers 的多语言文本向量化
- **统一存储**: 采用 DuckDB 高效存储结构化数据和向量表示

### 🔍 混合搜索引擎
- **语义搜索**: 基于 FAISS 的高性能向量相似度检索
- **结构化查询**: 支持精确匹配和条件过滤
- **混合排序**: 智能融合向量相似度和结构化查询结果
- **聚合分析**: 支持多维度数据分析和可视化

## 🛠️ 技术架构

- **存储层**: DuckDB
- **向量引擎**: FAISS + Sentence-Transformers
- **处理框架**: Pandas + NumPy
- **API接口**: FastAPI (计划中)

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

1. 文档预处理:
```python
from preprocess import main as preprocess_main

# 配置文档目录
input_dirs = ["path/to/your/documents"]

# 运行预处理
preprocess_main()
```

2. 搜索示例:
```python
from unified_search import SearchEngine

# 初始化搜索引擎
engine = SearchEngine()

# 语义搜索
results = engine.search("机器学习相关文档")

# 按文件类型搜索
results = engine.search("file:pdf")

# 按时间范围搜索
results = engine.search("date:2023-01-01 to 2023-12-31")
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

- 文档处理速度: ~100文档/秒
- 向量检索延迟: <50ms
- 支持文档规模: 百万级
- 向量维度: 384维

## 🗺️ 开发路线

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
- 团队主页: https://github.com/helixlife-ai

## 🙏 致谢

感谢以下开源项目:
- [Sentence-Transformers](https://github.com/UKPLab/sentence-transformers)
- [FAISS](https://github.com/facebookresearch/faiss)
- [DuckDB](https://github.com/duckdb/duckdb)
