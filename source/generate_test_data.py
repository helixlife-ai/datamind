import os
import json
import random
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

def create_test_data_folder():
    """创建测试数据文件夹"""
    base_path = Path("source/test_data")
    base_path.mkdir(parents=True, exist_ok=True)
    
    # 创建JSON测试数据
    users = [
        {
            "id": i,
            "name": f"用户{i}",
            "email": f"user{i}@example.com",
            "age": random.randint(18, 60),
            "tags": ["标签1", "标签2", "标签3"]
        } for i in range(1, 6)
    ]
    
    with open(base_path / "users.json", "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
    
    # 创建CSV测试数据
    products = pd.DataFrame({
        "产品ID": range(1, 11),
        "产品名称": [f"产品{i}" for i in range(1, 11)],
        "价格": [random.uniform(10, 1000) for _ in range(10)],
        "库存": [random.randint(0, 100) for _ in range(10)]
    })
    products.to_csv(base_path / "products.csv", index=False, encoding="utf-8")
    
    # 创建TXT测试数据
    with open(base_path / "notes.txt", "w", encoding="utf-8") as f:
        f.write("这是一个测试笔记文件\n")
        f.write("包含多行文本内容\n")
        f.write("用于测试文本文件的处理功能\n")
    
    # 创建XML测试数据
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<订单列表>
    <订单>
        <订单号>ORDER001</订单号>
        <客户名>张三</客户名>
        <金额>199.99</金额>
    </订单>
    <订单>
        <订单号>ORDER002</订单号>
        <客户名>李四</客户名>
        <金额>299.99</金额>
    </订单>
</订单列表>
"""
    with open(base_path / "orders.xml", "w", encoding="utf-8") as f:
        f.write(xml_content)
    
    # 创建Excel测试数据
    employees = pd.DataFrame({
        "员工ID": range(1, 6),
        "姓名": ["张三", "李四", "王五", "赵六", "钱七"],
        "部门": ["技术部", "市场部", "销售部", "人事部", "财务部"],
        "入职日期": [
            (datetime.now() - timedelta(days=random.randint(0, 365))).strftime("%Y-%m-%d")
            for _ in range(5)
        ]
    })
    employees.to_excel(base_path / "employees.xlsx", index=False)
    
    # 创建Markdown测试数据
    markdown_content = """# 项目文档

## 简介
这是一个测试用的Markdown文件。

## 功能特点
- 支持多种文件格式
- 自动数据处理
- 向量化存储

## 使用说明
1. 安装依赖
2. 运行程序
3. 查看结果
"""
    with open(base_path / "document.md", "w", encoding="utf-8") as f:
        f.write(markdown_content)
    
    # 创建AI相关的Markdown文档
    ai_markdown_content = """# 人工智能基础知识

## 什么是人工智能？
人工智能(AI)是一门让计算机模拟人类智能的科学技术，包括学习、推理、感知等能力。

## 机器学习基础概念
- 监督学习：通过标记数据进行训练
- 无监督学习：从未标记数据中发现模式
- 强化学习：通过奖惩机制学习最优策略

## 深度学习简介
深度学习是机器学习的一个子领域，使用多层神经网络进行特征学习和模式识别。

## 大语言模型(LLM)
大语言模型是基于Transformer架构的深度学习模型，能够理解和生成人类语言。
"""
    with open(base_path / "ai_guide.md", "w", encoding="utf-8") as f:
        f.write(ai_markdown_content)
    
    # 创建AI相关的JSON数据
    ai_models = [
        {
            "id": 1,
            "name": "GPT-4",
            "type": "大语言模型",
            "company": "OpenAI",
            "release_date": "2023",
            "features": ["自然语言处理", "代码生成", "多模态理解"]
        },
        {
            "id": 2,
            "name": "BERT",
            "type": "预训练语言模型",
            "company": "Google",
            "release_date": "2018",
            "features": ["双向编码", "文本表示", "迁移学习"]
        }
    ]
    with open(base_path / "ai_models.json", "w", encoding="utf-8") as f:
        json.dump(ai_models, f, ensure_ascii=False, indent=2)
    
    # 创建AI相关的CSV数据
    ml_algorithms = pd.DataFrame({
        "算法名称": ["决策树", "随机森林", "支持向量机", "神经网络", "K近邻"],
        "类型": ["监督学习", "集成学习", "监督学习", "深度学习", "监督学习"],
        "适用场景": ["分类/回归", "分类/回归", "分类", "分类/回归/聚类", "分类/回归"],
        "优点": ["可解释性强", "抗过拟合", "效果好", "表达能力强", "简单直观"],
        "缺点": ["容易过拟合", "计算量大", "对参数敏感", "需要大量数据", "计算复杂度高"]
    })
    ml_algorithms.to_csv(base_path / "ml_algorithms.csv", index=False, encoding="utf-8")
    
    # 创建AI相关的XML数据
    ai_xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<人工智能应用>
    <应用领域>
        <名称>计算机视觉</名称>
        <描述>使计算机能够理解和处理图像与视频</描述>
        <案例>
            <项目>人脸识别</项目>
            <项目>物体检测</项目>
            <项目>图像分割</项目>
        </案例>
    </应用领域>
    <应用领域>
        <名称>自然语言处理</名称>
        <描述>使计算机能够理解和生成人类语言</描述>
        <案例>
            <项目>机器翻译</项目>
            <项目>文本分类</项目>
            <项目>情感分析</项目>
        </案例>
    </应用领域>
</人工智能应用>
"""
    with open(base_path / "ai_applications.xml", "w", encoding="utf-8") as f:
        f.write(ai_xml_content)
    
    # 创建AI相关的Excel数据
    ai_companies = pd.DataFrame({
        "公司名称": ["OpenAI", "DeepMind", "百度", "腾讯", "阿里巴巴"],
        "主要产品": ["GPT系列", "AlphaGo", "文心一言", "混元", "通义千问"],
        "成立年份": [2015, 2010, 2000, 1998, 1999],
        "主要研究领域": ["大语言模型", "强化学习", "自然语言处理", "机器学习", "智能计算"],
        "代表性成果": ["ChatGPT", "AlphaFold", "飞桨", "天衍", "达摩院"]
    })
    ai_companies.to_excel(base_path / "ai_companies.xlsx", index=False)

if __name__ == "__main__":
    create_test_data_folder()
    print("测试数据生成完成！") 