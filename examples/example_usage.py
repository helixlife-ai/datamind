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

from datamind.services.alchemy_service import DataMindAlchemy




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
        
        # 创建DataMindAlchemy实例，传入logger
        alchemy = DataMindAlchemy(work_dir=work_dir, logger=logger)
        
        logger.info(f"测试查询: {query}")
        
        # 调用处理方法
        result = await alchemy.process(
            query=query,
            input_dirs=input_dirs
        )
        
        # 输出结果
        if result['status'] == 'success':
            logger.info("解析结果:\n%s", 
                json.dumps(result['results']['parsed_intent'], indent=2, ensure_ascii=False))
            logger.info("检索计划:\n%s", 
                json.dumps(result['results']['search_plan'], indent=2, ensure_ascii=False))
            
            if result['results']['search_results']:
                logger.info("\n搜索结果获取成功！")
                
                if result['results']['artifacts']:
                    logger.info("\n已生成以下制品文件:")
                    for artifact_path in result['results']['artifacts']:
                        logger.info("- %s", Path(artifact_path).name)
                    
                    # 输出优化建议信息
                    if result['results'].get('optimization_suggestions'):
                        logger.info("\n优化建议和结果:")
                        for suggestion in result['results']['optimization_suggestions']:
                            logger.info("- 优化建议: %s", suggestion['suggestion'])
                            logger.info("  来源: %s", suggestion['source'])
                            logger.info("  生成时间: %s", suggestion['timestamp'])
                            if suggestion['artifacts']:
                                logger.info("  生成的制品:")
                                for artifact in suggestion['artifacts']:
                                    logger.info("    - %s", Path(artifact).name)
                            logger.info("---")
                    
        else:
            logger.error("\n处理失败: %s", result.get('message', '未知错误'))
            
    except Exception as e:
        logger.error("数据炼丹测试失败: %s", str(e), exc_info=True)
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
            work_dir=script_dir.parent / "work_dir" / "data_alchemy",  
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