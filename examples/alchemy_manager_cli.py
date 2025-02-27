#!/usr/bin/env python
"""
DataMindAlchemy 任务管理命令行工具
"""

import os
import sys
import json
import argparse
from pathlib import Path
import logging
from tabulate import tabulate
from datetime import datetime
import shutil

# 添加项目根目录到Python路径
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from datamind import setup_logging
from datamind.services.alchemy_manager import AlchemyManager

def format_datetime(dt_str):
    """格式化日期时间字符串"""
    if not dt_str:
        return "未知"
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return dt_str

def list_tasks(manager, args):
    """列出所有任务"""
    tasks = manager.get_all_tasks(include_archived=args.all)
    
    if args.status:
        tasks = [t for t in tasks if t.get("status") == args.status]
    
    if args.tag:
        tasks = [t for t in tasks if args.tag in t.get("tags", [])]
    
    if args.query:
        query_results = manager.search_tasks(args.query)
        task_ids = {t["id"] for t in query_results}
        tasks = [t for t in tasks if t["id"] in task_ids]
    
    if not tasks:
        print("未找到任务")
        return
    
    # 准备表格数据
    table_data = []
    for task in tasks:
        status = task.get("status", "未知")
        status_display = {
            "created": "已创建",
            "processing": "处理中",
            "completed": "已完成",
            "error": "出错",
            "cancelled": "已取消"
        }.get(status, status)
        
        archived = "是" if task.get("is_archived") else "否"
        
        row = [
            task["id"],
            task.get("name", ""),
            task.get("latest_query", "")[:30] + ("..." if len(task.get("latest_query", "")) > 30 else ""),
            status_display,
            task.get("iterations", 0),
            task.get("artifacts_count", 0),
            format_datetime(task.get("updated_at")),
            ", ".join(task.get("tags", [])),
            archived
        ]
        table_data.append(row)
    
    # 按更新时间排序
    table_data.sort(key=lambda x: x[6], reverse=True)
    
    # 输出表格
    headers = ["ID", "名称", "查询", "状态", "迭代数", "制品数", "更新时间", "标签", "已归档"]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    print(f"共 {len(table_data)} 个任务")

def show_task(manager, args):
    """显示任务详情"""
    task = manager.get_task(args.id)
    if not task:
        print(f"任务 {args.id} 不存在")
        return
    
    print(f"任务ID: {task['id']}")
    print(f"名称: {task.get('name', '')}")
    print(f"描述: {task.get('description', '')}")
    print(f"状态: {task.get('status', '未知')}")
    print(f"迭代次数: {task.get('iterations', 0)}")
    print(f"最新查询: {task.get('latest_query', '')}")
    print(f"标签: {', '.join(task.get('tags', []))}")
    print(f"创建时间: {format_datetime(task.get('created_at'))}")
    print(f"更新时间: {format_datetime(task.get('updated_at'))}")
    print(f"已归档: {'是' if task.get('is_archived') else '否'}")
    
    # 显示制品列表
    artifacts = task.get("artifacts", [])
    if artifacts:
        print("\n制品列表:")
        for i, artifact in enumerate(artifacts, 1):
            print(f"  {i}. {artifact}")
        
        if task.get("artifacts_count", 0) > len(artifacts):
            print(f"  ... 共 {task.get('artifacts_count')} 个制品")
    
    # 显示继续执行的命令
    print("\n继续此任务:")
    print(f"  python examples/example_usage.py --mode=continue --id={task['id']}")
    
    # 显示恢复执行的命令
    print("\n从中断点恢复此任务:")
    print(f"  python examples/example_usage.py --mode=continue --id={task['id']} --resume")

def rename_task(manager, args):
    """重命名任务"""
    task = manager.get_task(args.id)
    if not task:
        print(f"任务 {args.id} 不存在")
        return
    
    manager.update_task(args.id, {"name": args.name})
    print(f"已将任务 {args.id} 重命名为 '{args.name}'")

def describe_task(manager, args):
    """更新任务描述"""
    task = manager.get_task(args.id)
    if not task:
        print(f"任务 {args.id} 不存在")
        return
    
    manager.update_task(args.id, {"description": args.description})
    print(f"已更新任务 {args.id} 的描述")

def tag_task(manager, args):
    """为任务添加标签"""
    tags = args.tags.split(",")
    task = manager.get_task(args.id)
    if not task:
        print(f"任务 {args.id} 不存在")
        return
    
    for tag in tags:
        tag = tag.strip()
        if tag:
            manager.tag_task(args.id, tag)
    
    print(f"已为任务 {args.id} 添加标签: {args.tags}")

def untag_task(manager, args):
    """移除任务标签"""
    task = manager.get_task(args.id)
    if not task:
        print(f"任务 {args.id} 不存在")
        return
    
    manager.untag_task(args.id, args.tag)
    print(f"已从任务 {args.id} 移除标签: {args.tag}")

def archive_task(manager, args):
    """归档任务"""
    task = manager.get_task(args.id)
    if not task:
        print(f"任务 {args.id} 不存在")
        return
    
    manager.archive_task(args.id)
    print(f"已归档任务 {args.id}")

def unarchive_task(manager, args):
    """取消归档任务"""
    task = manager.get_task(args.id)
    if not task:
        print(f"任务 {args.id} 不存在")
        return
    
    manager.unarchive_task(args.id)
    print(f"已取消归档任务 {args.id}")

def delete_task(manager, args):
    """删除任务"""
    task = manager.get_task(args.id)
    if not task:
        print(f"任务 {args.id} 不存在")
        return
    
    if not args.force:
        confirm = input(f"确定要删除任务 {args.id} 吗？此操作不可撤销 [y/N]: ")
        if confirm.lower() not in ["y", "yes"]:
            print("已取消删除")
            return
    
    success = manager.delete_task(args.id, delete_files=args.files)
    if success:
        print(f"已删除任务 {args.id}" + (" 及其所有文件" if args.files else ""))
    else:
        print(f"删除任务 {args.id} 失败")

def export_tasks(manager, args):
    """导出任务列表"""
    output_path = manager.export_tasks_to_csv(args.output)
    print(f"已将任务列表导出到 {output_path}")

def scan_tasks(manager, args):
    """扫描任务"""
    manager.scan_existing_tasks()
    print("已扫描现有任务")

def list_resumable_tasks(manager, args):
    """列出所有可恢复的任务"""
    resumable_tasks = manager.get_resumable_tasks()
    
    if not resumable_tasks:
        print("未找到可恢复的任务")
        return
    
    # 准备表格数据
    table_data = []
    for i, task in enumerate(resumable_tasks, 1):
        resume_info = task.get("resume_info", {})
        timestamp = resume_info.get("timestamp", "未知时间")
        current_step = resume_info.get("current_step", "未知")
        
        try:
            dt = datetime.fromisoformat(timestamp)
            timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            pass
        
        row = [
            i,
            task["id"],
            task.get("name", ""),
            task.get("latest_query", "")[:30] + ("..." if len(task.get("latest_query", "")) > 30 else ""),
            current_step,
            timestamp,
            "python examples/example_usage.py --mode=continue --id=%s --resume" % task["id"]
        ]
        table_data.append(row)
    
    # 输出表格
    headers = ["序号", "ID", "名称", "查询", "中断步骤", "时间", "恢复命令"]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    print(f"共 {len(table_data)} 个可恢复任务")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="DataMindAlchemy 任务管理工具")
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # 通用选项
    parser.add_argument("--work-dir", type=str, default=str(project_root / "work_dir"),
                      help="工作目录路径")
    
    # list 命令
    list_parser = subparsers.add_parser("list", help="列出所有任务")
    list_parser.add_argument("--all", action="store_true", help="包括已归档的任务")
    list_parser.add_argument("--status", type=str, help="按状态筛选")
    list_parser.add_argument("--tag", type=str, help="按标签筛选")
    list_parser.add_argument("--query", type=str, help="搜索关键词")
    list_parser.set_defaults(func=list_tasks)
    
    # show 命令
    show_parser = subparsers.add_parser("show", help="显示任务详情")
    show_parser.add_argument("id", type=str, help="任务ID")
    show_parser.set_defaults(func=show_task)
    
    # rename 命令
    rename_parser = subparsers.add_parser("rename", help="重命名任务")
    rename_parser.add_argument("id", type=str, help="任务ID")
    rename_parser.add_argument("name", type=str, help="新名称")
    rename_parser.set_defaults(func=rename_task)
    
    # describe 命令
    describe_parser = subparsers.add_parser("describe", help="更新任务描述")
    describe_parser.add_argument("id", type=str, help="任务ID")
    describe_parser.add_argument("description", type=str, help="新描述")
    describe_parser.set_defaults(func=describe_task)
    
    # tag 命令
    tag_parser = subparsers.add_parser("tag", help="为任务添加标签")
    tag_parser.add_argument("id", type=str, help="任务ID")
    tag_parser.add_argument("tags", type=str, help="标签(逗号分隔)")
    tag_parser.set_defaults(func=tag_task)
    
    # untag 命令
    untag_parser = subparsers.add_parser("untag", help="移除任务标签")
    untag_parser.add_argument("id", type=str, help="任务ID")
    untag_parser.add_argument("tag", type=str, help="要移除的标签")
    untag_parser.set_defaults(func=untag_task)
    
    # archive 命令
    archive_parser = subparsers.add_parser("archive", help="归档任务")
    archive_parser.add_argument("id", type=str, help="任务ID")
    archive_parser.set_defaults(func=archive_task)
    
    # unarchive 命令
    unarchive_parser = subparsers.add_parser("unarchive", help="取消归档任务")
    unarchive_parser.add_argument("id", type=str, help="任务ID")
    unarchive_parser.set_defaults(func=unarchive_task)
    
    # delete 命令
    delete_parser = subparsers.add_parser("delete", help="删除任务")
    delete_parser.add_argument("id", type=str, help="任务ID")
    delete_parser.add_argument("--force", "-f", action="store_true", help="强制删除，不提示确认")
    delete_parser.add_argument("--files", action="store_true", help="同时删除任务文件")
    delete_parser.set_defaults(func=delete_task)
    
    # export 命令
    export_parser = subparsers.add_parser("export", help="导出任务列表")
    export_parser.add_argument("--output", "-o", type=str, help="输出文件路径")
    export_parser.set_defaults(func=export_tasks)
    
    # scan 命令
    scan_parser = subparsers.add_parser("scan", help="扫描现有任务")
    scan_parser.set_defaults(func=scan_tasks)
    
    # resumable 命令
    resumable_parser = subparsers.add_parser("resumable", help="列出可恢复的任务")
    resumable_parser.set_defaults(func=list_resumable_tasks)
    
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return
    
    # 初始化日志
    logger = setup_logging()
    
    # 创建任务管理器
    work_dir = Path(args.work_dir)
    manager = AlchemyManager(work_dir=work_dir, logger=logger)
    
    # 执行命令
    args.func(manager, args)

if __name__ == "__main__":
    main() 