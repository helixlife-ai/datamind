import os
import sys
import json
import asyncio
from pathlib import Path
import logging
import argparse

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


async def continue_datamind_alchemy(
    alchemy_id: str,
    query: str = None,
    input_dirs: list = None,
    work_dir: Path = None,
    logger: logging.Logger = None   
) -> None:
    """继续已有的数据炼丹流程"""
    logger = logger or logging.getLogger(__name__)
    
    try:
        logger.info("\n=== 继续数据炼丹流程 ===")
        logger.info(f"继续的alchemy_id: {alchemy_id}")
        
        # 创建DataMindAlchemy实例，传入指定的alchemy_id
        alchemy = DataMindAlchemy(work_dir=work_dir, logger=logger, alchemy_id=alchemy_id)
        
        logger.info(f"新的查询: {query}")
        
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
        logger.error("继续数据炼丹失败: %s", str(e), exc_info=True)
        raise


async def async_main():
    """异步主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='数据炼丹测试和继续')
    parser.add_argument('--query', type=str, help='查询文本')
    parser.add_argument('--config', type=str, help='配置文件路径', default='work_dir/config.json')
    parser.add_argument('--mode', type=str, choices=['new', 'continue'], help='运行模式: new(新建) 或 continue(继续)')
    parser.add_argument('--id', type=str, help='要继续的alchemy_id（仅在continue模式下有效）')
    args = parser.parse_args()
    
    logger = setup_logging()
    logger.info("开始运行数据炼丹程序")
    
    try:        
        # 创建工作目录
        script_dir = Path(__file__).parent
        work_dir = script_dir.parent / "work_dir"
        test_data_dir = work_dir / "test_data"

        # 初始化默认参数
        query = args.query or "请生成一份关于AI发展的报告"
        input_dirs = [str(test_data_dir)]
        mode = args.mode or "new"  # 默认为新建模式
        alchemy_id = args.id
        
        # 首先尝试从配置文件读取
        config_path = Path(args.config)
        if config_path.exists():
            logger.info(f"从配置文件加载: {config_path}")
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                query = config.get('query', query)
                if config.get('input_dirs'):
                    input_dirs = config.get('input_dirs')
                    logger.info(f"从配置中读取input_dirs: {input_dirs}")
                # 读取运行模式
                mode = config.get('mode', mode)
                # 在continue模式下读取alchemy_id
                if mode == "continue":
                    alchemy_id = config.get('alchemy_id', alchemy_id)
        
        # 命令行参数优先级高于配置文件
        if args.query:
            query = args.query
        if args.mode:
            mode = args.mode
        if args.id:
            alchemy_id = args.id
        
        # 根据模式执行不同的处理
        if mode == "continue":
            # 继续模式：检查是否提供了必要的alchemy_id
            if not alchemy_id:
                logger.error("错误: 在continue模式下必须提供alchemy_id！使用--id参数或在配置文件中指定")
                return
            
            logger.info(f"运行模式: 继续已有炼丹流程 (alchemy_id: {alchemy_id})")
            await continue_datamind_alchemy(
                alchemy_id=alchemy_id,
                query=query,
                input_dirs=input_dirs,
                work_dir=work_dir / "data_alchemy",  
                logger=logger
            )
            logger.info("继续数据炼丹流程完成")
        else:
            # 新建模式：执行标准数据炼丹流程
            logger.info("运行模式: 新建炼丹流程")
            logger.info(f"开始数据炼丹测试，查询: {query}")
            await datamind_alchemy_test(
                query=query,
                input_dirs=input_dirs,
                work_dir=work_dir / "data_alchemy",  
                logger=logger
            )
            logger.info("数据炼丹测试完成")
        
        logger.info("程序运行完成")
        
    except Exception as e:
        logger.error(f"程序运行失败: {str(e)}", exc_info=True)
        raise

def main():
    """同步主函数入口"""
    asyncio.run(async_main())

if __name__ == "__main__":
    main() 