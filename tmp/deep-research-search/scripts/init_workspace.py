"""
深度研究工作目录初始化脚本

功能：
  1. 创建标准目录结构
  2. 初始化各文件（报告骨架、知识图谱索引、评分文件）
  3. 输出创建结果

用法：
  python init_workspace.py --keyword <关键词> [--base-dir <基目录>]

示例：
  python init_workspace.py --keyword rust异步 --base-dir works/tmp
  → 创建 works/tmp/2026042114-rust异步/
"""

import argparse
import os
from datetime import datetime


WORKSPACE_TEMPLATE = """
{workdir}/
├── graph/
│   └── _index.md         # 知识图谱索引
├── data/
│   ├── round-1/ ~ round-6/
├── urls/
│   ├── round-1/ ~ round-6/
└── scores.md             # 轮次进度
"""

GRAPH_INDEX_TEMPLATE = """# 知识图谱索引

> 自动维护，记录所有概念节点及其关联数

| 概念 | 关联数 | 文件 |
|------|--------|------|
"""

SCORES_TEMPLATE = """# 研究进度

> 每轮（采集→获取→兜底→消化）完成后，运行 `python scripts/health.py {workdir} --round N` 追加健康度块：
> 采集达成率 / 获取成功率 / CDP 兜底率 / 图谱节点·洞察数。

"""


def create_workspace(keyword: str, base_dir: str = 'works/tmp') -> str:
    """创建工作目录并初始化文件"""
    now = datetime.now()
    timestamp = now.strftime('%Y%m%d%H')

    # 清理关键词：去除特殊字符，限制长度
    safe_keyword = ''.join(c for c in keyword if c.isalnum() or c in '_-').strip('-_')
    if len(safe_keyword) > 6:
        safe_keyword = safe_keyword[:6]

    dir_name = f"{timestamp}-{safe_keyword}"
    workspace = os.path.join(base_dir, dir_name)
    workspace = os.path.normpath(workspace)

    # 创建目录结构
    dirs_to_create = [
        workspace,
        os.path.join(workspace, 'graph'),
        os.path.join(workspace, 'data'),
        os.path.join(workspace, 'urls'),
    ]
    for i in range(1, 7):
        dirs_to_create.append(os.path.join(workspace, 'data', f'round-{i}'))
        dirs_to_create.append(os.path.join(workspace, 'urls', f'round-{i}'))

    for d in dirs_to_create:
        os.makedirs(d, exist_ok=True)

    # 创建初始化文件
    files = {
        os.path.join(workspace, 'graph', '_index.md'):
            GRAPH_INDEX_TEMPLATE,
        os.path.join(workspace, 'scores.md'):
            SCORES_TEMPLATE,
    }

    for filepath, content in files.items():
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

    return workspace


def main():
    parser = argparse.ArgumentParser(description='深度研究工作目录初始化')
    parser.add_argument('--keyword', '-k', required=True, help='研究主题关键词')
    parser.add_argument('--base-dir', '-d', default='works/tmp', help='基目录（默认 works/tmp）')
    args = parser.parse_args()

    workspace = create_workspace(args.keyword, args.base_dir)

    # 输出结果
    print(f"workspace={workspace}")
    print(f"keyword={args.keyword}")
    print(f"\n目录结构：")
    for root, dirs, files in os.walk(workspace):
        level = root.replace(workspace, '').count(os.sep)
        indent = '  ' * level
        dirname = os.path.basename(root)
        print(f"{indent}{dirname}/")
        sub_indent = '  ' * (level + 1)
        for file in sorted(files):
            print(f"{sub_indent}{file}")


if __name__ == '__main__':
    main()
