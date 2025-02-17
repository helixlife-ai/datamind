import os
import sys
import json
import asyncio
from pathlib import Path
import logging

# 添加项目根目录到Python路径
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from datamind import (
    setup_logging
)

from datamind.core.feedback_optimizer import FeedbackOptimizer
from datamind.services.alchemy_service import DataMindAlchemy


async def run_test_optimization(
    feedback_optimizer: FeedbackOptimizer, 
    alchemy_dir: str,
    logger: logging.Logger = None
) -> None:
    """运行反馈优化测试流程
    
    Args:
        feedback_optimizer: 反馈优化器实例
        alchemy_dir: 炼丹工作流运行目录
    """
    logger = logger or logging.getLogger(__name__)
    logger.info("\n=== 开始反馈优化流程测试 ===")
        
    # 示例反馈
    test_feedbacks = [
        "请在AI趋势分析中增加更多关于大模型发展的内容",
        "希望在报告中补充更多实际应用案例"
    ]
    
    # 创建DataMindAlchemy实例
    alchemy = DataMindAlchemy(work_dir=Path(alchemy_dir) / "iteration")
    
    # 执行多轮反馈优化
    for i, feedback in enumerate(test_feedbacks, 1):
        logger.info(f"\n第{i}轮反馈优化:")
        logger.info(f"用户反馈: {feedback}")
        
        # 将反馈写入feedback.txt
        feedback_file = Path(alchemy_dir) / "feedback.txt"
        with open(feedback_file, "w", encoding="utf-8") as f:
            f.write(feedback)
        
        # 生成反馈上下文
        context_result = await feedback_optimizer.feedback_to_context(alchemy_dir)
        
        if context_result['status'] == 'success':
            logger.info("反馈上下文生成成功！")
            
            # 使用新查询重新执行工作流
            alchemy_result = await alchemy.process(
                query=context_result['context']['current_query'],
                input_dirs=None,  # 使用已有数据
                context=context_result['context']  # 传入完整上下文
            )
            
            if alchemy_result['status'] == 'success':
                logger.info("基于反馈的新一轮处理成功！")
                if alchemy_result['results']['delivery_plan']:
                    # 更新当前目录为新的运行目录
                    alchemy_dir = str(Path(alchemy_result['results']['delivery_plan']['_file_paths']['base_dir']).parent)
                    logger.info(f"新的交付文件保存在: {alchemy_dir}/delivery")
            else:
                logger.error(f"新一轮处理失败: {alchemy_result['message']}")
                break
        else:
            logger.error(f"反馈上下文生成失败: {context_result['message']}")
            break
            
    logger.info("\n反馈优化流程测试完成")

async def datamind_alchemy_test(
    query: str = None,
    input_dirs: list = None,
    work_dir: Path = None,
    logger: logging.Logger = None   
) -> None:
    """数据炼丹测试"""
    logger = logger or logging.getLogger(__name__)
    
    try:
        logger.info("\n=== 数据炼丹测试 ===")
        
        # 创建DataMindAlchemy实例
        alchemy = DataMindAlchemy(work_dir=work_dir, logger=logger)
        
        logger.info(f"测试查询: {query}")
        
        
        # 调用处理方法
        result = await alchemy.process(
            query=query,
            input_dirs=input_dirs
        )
        
        # 输出结果
        if result['status'] == 'success':
            logger.info("解析结果:", json.dumps(result['results']['parsed_intent'], indent=2, ensure_ascii=False))
            logger.info("检索计划:", json.dumps(result['results']['search_plan'], indent=2, ensure_ascii=False))
            
            logger.info("\n检索结果摘要:")
            if 'formatted' in result['results']['search_results']:
                logger.info(result['results']['search_results']['formatted'])
            else:
                logger.info("总记录数:", result['results']['search_results'].get('stats', {}).get('total', 0))
            
            if result['results']['delivery_plan']:
                logger.info("\n交付计划生成成功！")
                delivery_dir = result['results']['delivery_plan']['_file_paths']['base_dir']
                logger.info(f"相关文件保存在: {delivery_dir}")
                
                if result['results']['generated_files']:
                    logger.info("\n已生成以下交付文件:")
                    for file_path in result['results']['generated_files']:
                        logger.info(f"- {Path(file_path).name}")
                    
                    # 运行反馈优化流程
                    await run_test_optimization(
                        feedback_optimizer=result['components']['feedback_optimizer'],
                        alchemy_dir=str(Path(delivery_dir).parent),
                        logger=logger
                    )
        else:
            logger.error(f"\n处理失败: {result.get('message', '未知错误')}")
            
    except Exception as e:
        logger.error(f"数据炼丹测试失败: {str(e)}", exc_info=True)
        raise

async def async_main():
    """异步主函数"""
    logger = setup_logging()
    logger.info("开始运行测试程序")
    
    try:        
        # 创建工作目录
        script_dir = Path(__file__).parent
        test_data_dir = script_dir.parent / "work_dir" / "test_data"

        # 初始化默认查询
        query = "请生成一份关于AI发展的报告"
        
        try:
            # 从work_dir/query.txt中读取测试查询  
            query_file = script_dir.parent / "work_dir" / "query.txt"
            with open(query_file, "r", encoding="utf-8") as f:
                file_query = f.read().strip()
                if file_query:  # 只在文件内容非空时更新查询
                    query = file_query
        except Exception as e:
            pass

        # 执行数据炼丹测试
        logger.info("开始数据炼丹测试")
        await datamind_alchemy_test(
            query=query,
            input_dirs=[str(test_data_dir)],
            work_dir=script_dir.parent / "work_dir" / "output" / "alchemy_runs",  # 路径调整
            logger=logger
        )
        logger.info("数据炼丹测试完成")
        
        logger.info("测试程序运行完成")
        
    except Exception as e:
        logger.error(f"程序运行失败: {str(e)}", exc_info=True)
        raise

def main():
    """同步主函数入口"""
    asyncio.run(async_main())

if __name__ == "__main__":
    main() 