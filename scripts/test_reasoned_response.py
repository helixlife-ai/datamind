import asyncio
import os
from datamind.models.model_manager import ModelManager, ModelConfig
from datamind.config.settings import DEFAULT_REASONING_MODEL, DEFAULT_LLM_API_BASE, DEFAULT_LLM_API_KEY
import logging

# 配置日志
logging.basicConfig(level=logging.DEBUG)

async def test_reasoned_response():
    # 创建ModelManager实例
    manager = ModelManager()
    
    # 注册推理模型
    reasoning_config = ModelConfig(
        name=DEFAULT_REASONING_MODEL,
        model_type="api",
        api_base=DEFAULT_LLM_API_BASE,
        api_key=DEFAULT_LLM_API_KEY
    )
    manager.register_model(reasoning_config)
    
    # 测试消息
    messages = [
        {"role": "system", "content": "你是一个专业的数据分析和内容组织专家。请根据用户的检索需求和获得的结果，生成一个详细的交付计划。"},
        {"role": "user", "content": "解释一下为什么太阳看起来是黄色的？"}
    ]
    
    # 调用generate_reasoned_response
    response = await manager.generate_reasoned_response(
        messages=messages
    )
    
    if response:
        print("\n=== API响应 ===")
        reasoning_content = response.choices[0].message.reasoning_content
        content = response.choices[0].message.content
        print(f"推理过程: {reasoning_content}")
        print(f"最终回答: {content}")

    else:
        print("生成响应失败")

if __name__ == "__main__":       
    # 运行测试
    asyncio.run(test_reasoned_response()) 