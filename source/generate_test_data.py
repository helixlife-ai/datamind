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

if __name__ == "__main__":
    create_test_data_folder()
    print("测试数据生成完成！") 