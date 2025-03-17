#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
将指定文件夹中的HTML文件部署到GitHub仓库并生成GitHub Pages
"""

import os
import sys
import shutil
import subprocess
import argparse
from datetime import datetime
from dotenv import load_dotenv

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='将HTML文件部署到GitHub Pages')
    parser.add_argument('source_dir', help='包含HTML文件的源目录')
    parser.add_argument('--repo', required=True, help='GitHub仓库URL')
    parser.add_argument('--branch', default='gh-pages', help='GitHub Pages分支名称（默认：gh-pages）')
    parser.add_argument('--commit-message', default=None, help='自定义提交信息')
    parser.add_argument('--temp-dir', default='./temp_deploy', help='临时目录路径')
    parser.add_argument('--token', help='GitHub个人访问令牌(PAT)，如不提供将尝试从.env文件读取GITHUB_TOKEN')
    parser.add_argument('--env-file', default='.env', help='.env文件路径（默认：.env）')
    return parser.parse_args()

def run_command(command, cwd=None):
    """执行shell命令并打印输出"""
    print(f"执行: {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"错误: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()

def deploy_to_github(source_dir, repo_url, branch, commit_message, temp_dir, token=None):
    """将源目录中的文件部署到GitHub Pages"""
    # 确保源目录存在
    if not os.path.isdir(source_dir):
        print(f"错误: 源目录 '{source_dir}' 不存在")
        sys.exit(1)
    
    # 如果提供了token，修改repo_url以包含token
    original_repo_url = repo_url
    if token and repo_url.startswith('https://'):
        # 将https://github.com/user/repo.git转换为https://token@github.com/user/repo.git
        repo_parts = repo_url.split('://')
        repo_url = f"{repo_parts[0]}://{token}@{repo_parts[1]}"
    
    # 创建临时目录
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    try:
        # 克隆仓库的指定分支（如果存在）
        clone_command = ['git', 'clone', repo_url, '--branch', branch, '--single-branch', temp_dir]
        try:
            run_command(clone_command)
            # 清空临时目录中的所有文件（保留.git目录）
            for item in os.listdir(temp_dir):
                if item != '.git':
                    item_path = os.path.join(temp_dir, item)
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
        except:
            # 如果分支不存在，则创建一个新的空仓库
            print(f"分支 '{branch}' 不存在，创建新分支...")
            os.makedirs(os.path.join(temp_dir, '.git'), exist_ok=True)
            run_command(['git', 'init'], cwd=temp_dir)
            run_command(['git', 'remote', 'add', 'origin', repo_url], cwd=temp_dir)
            run_command(['git', 'checkout', '-b', branch], cwd=temp_dir)
        
        # 复制源目录中的所有文件到临时目录
        for item in os.listdir(source_dir):
            source_path = os.path.join(source_dir, item)
            dest_path = os.path.join(temp_dir, item)
            if os.path.isdir(source_path):
                shutil.copytree(source_path, dest_path)
            else:
                shutil.copy2(source_path, dest_path)
        
        # 创建.nojekyll文件（防止GitHub Pages使用Jekyll处理）
        with open(os.path.join(temp_dir, '.nojekyll'), 'w') as f:
            pass
        
        # 添加所有文件到Git
        run_command(['git', 'add', '--all'], cwd=temp_dir)
        
        # 设置默认提交信息
        if not commit_message:
            commit_message = f"更新网站内容 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # 提交更改
        run_command(['git', 'commit', '-m', commit_message], cwd=temp_dir)
        
        # 推送到GitHub
        run_command(['git', 'push', '-u', 'origin', branch], cwd=temp_dir)
        
        print(f"部署成功！GitHub Pages将很快在以下地址可用:")
        # 从仓库URL中提取用户名和仓库名（使用原始URL，不包含token）
        repo_parts = original_repo_url.rstrip('/').split('/')
        user_repo = '/'.join(repo_parts[-2:])
        user_repo = user_repo.replace('.git', '')
        print(f"https://{user_repo.split('/')[0]}.github.io/{user_repo.split('/')[1]}/")
        
    finally:
        # 清理临时目录
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    args = parse_arguments()
    
    # 尝试从.env文件加载环境变量
    load_dotenv(args.env_file)
    
    # 优先使用命令行参数中的token，如果没有则尝试从环境变量获取
    token = args.token or os.environ.get('GITHUB_TOKEN')
    
    if not token and args.repo.startswith('https://'):
        print("警告: 未提供GitHub令牌。如需使用令牌认证，请通过--token参数提供或在.env文件中设置GITHUB_TOKEN")
    
    deploy_to_github(
        args.source_dir,
        args.repo,
        args.branch,
        args.commit_message,
        args.temp_dir,
        token
    ) 