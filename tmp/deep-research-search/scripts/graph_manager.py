"""
知识图谱双向链接管理脚本（v2 路 B：schema-agnostic）

功能：
  1. link    — 建立双向链接（支持描述）
  2. verify  — 校验完整性：[[双链]]拓扑 + 基本内容完整性（schema-agnostic）
  3. export  — 导出概览：统计通用结构（section/子节块/表格/双链/信度），不绑特定模板

路 B 设计（解决双轨制）：
  原版 export 统计依赖 V3 的"关键事实/时间线/争议"等特定 section 名，
  套到 V3.1 的 template-catalog 节点（核心判断/洞察/未解张力）会失准。
  本版统计改为 schema-agnostic：数 ## section、### 子节块、表格行、[[双链]]、信度标记，
  无论节点用哪套模板都能给出有意义的丰富度。
  _index.md 增"邻居"列（连接拓扑），支撑 graph-refine-prompt 的簇分组。

数据格式：
  - 节点文件：graph/{slug}.md
  - [[概念名]] 双链；_index.md 索引（含邻居拓扑）

用法：
  python graph_manager.py -g <graph目录> link <源> <目标> [-t <关系>] [--desc <描述>] [--source-file <来源>]
  python graph_manager.py -g <graph目录> verify
  python graph_manager.py -g <graph目录> export
"""

import argparse
import os
import re
import sys
from collections import defaultdict


def slugify(name: str) -> str:
    slug = ''.join(c if c.isalnum() or c in '_-' else '-' for c in name)
    slug = slug.strip('-')
    return slug.lower()


def read_node(filepath: str) -> dict:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    links = re.findall(r'\[\[([^\]]+)\]\]', content)
    title_match = re.search(r'^# (.+)$', content, re.MULTILINE)
    concept_name = title_match.group(1) if title_match else os.path.splitext(os.path.basename(filepath))[0]
    return {
        'path': filepath,
        'content': content,
        'links': links,
        'name': concept_name,
    }


def get_all_nodes(graph_dir: str) -> dict[str, dict]:
    nodes = {}
    if not os.path.exists(graph_dir):
        return nodes
    for filename in os.listdir(graph_dir):
        if filename.startswith('_') or not filename.endswith('.md'):
            continue
        filepath = os.path.join(graph_dir, filename)
        node = read_node(filepath)
        nodes[node['name']] = node
    return nodes


def node_filepath(graph_dir: str, name: str) -> str:
    return os.path.join(graph_dir, f"{slugify(name)}.md")


def update_index(graph_dir: str, nodes: dict):
    """_index.md：概念索引 + 邻居拓扑（支撑簇分组）。"""
    index_path = os.path.join(graph_dir, '_index.md')
    lines = [
        "# 知识图谱索引\n",
        "| 概念 | 关联数 | 邻居 | 文件 |",
        "|------|--------|------|------|",
    ]
    sorted_nodes = sorted(nodes.items(), key=lambda x: len(x[1]['links']), reverse=True)
    for name, node in sorted_nodes:
        rel_path = os.path.relpath(node['path'], graph_dir)
        links = node['links']
        neighbors = ', '.join(f'[[{l}]]' for l in links[:5])
        if len(links) > 5:
            neighbors += f' +{len(links) - 5}'
        lines.append(f"| [[{name}]] | {len(links)} | {neighbors or '—'} | {rel_path} |")
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def cmd_link(args):
    graph_dir = args.graph_dir
    source_path = node_filepath(graph_dir, args.source)
    target_path = node_filepath(graph_dir, args.target)

    for path, name in [(source_path, args.source), (target_path, args.target)]:
        if not os.path.exists(path):
            print(f"错误: 节点不存在 — {name} ({path})")
            sys.exit(1)

    relation_text = f" ({args.relation})" if args.relation else ""
    desc_text = f": {args.desc}" if getattr(args, 'desc', None) else ""
    source_tag = f" [来源: {args.source_file}]" if getattr(args, 'source_file', None) else ""

    link_line_source = f"- [[{args.target}]] — {args.relation or '关联'}{desc_text}{source_tag}"
    link_line_target = f"- [[{args.source}]] — {args.relation or '关联'}{desc_text}{source_tag}"

    for path, link_line, target_name in [
        (source_path, link_line_source, args.target),
        (target_path, link_line_target, args.source),
    ]:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        if f"[[{target_name}]]" not in content:
            header = "## 关联概念\n"
            if header in content:
                content = content.replace(header, f"{header}{link_line}\n", 1)
            else:
                content = content.rstrip() + f"\n\n## 关联概念\n{link_line}\n"
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)

    print(f"已建立双向链接: [[{args.source}]] <-> [[{args.target}]]{relation_text}{desc_text}")
    nodes = get_all_nodes(graph_dir)
    update_index(graph_dir, nodes)


def cmd_verify(args):
    """校验：[[双链]]拓扑完整 + 基本内容完整性（schema-agnostic）。"""
    graph_dir = args.graph_dir
    nodes = get_all_nodes(graph_dir)
    if not nodes:
        print("图谱为空，无内容可验证。")
        return
    issues = []
    for name, node in nodes.items():
        # 1. 双链拓扑
        for linked_concept in node['links']:
            if linked_concept not in nodes:
                issues.append(f"[缺少节点] [[{name}]] 链接到不存在的 [[{linked_concept}]]")
                continue
            target_node = nodes[linked_concept]
            if name not in target_node['links']:
                issues.append(f"[缺少反向链接] [[{name}]] → [[{linked_concept}]]，但反向缺失")
        # 2. 基本完整性（schema-agnostic）：至少有核心判断/摘要，或正文足够长
        content = node['content']
        has_judgment = ('## 核心判断' in content) or ('## 摘要' in content)
        if not has_judgment and len(content.strip()) < 200:
            issues.append(f"[内容过少] [[{name}]] 无核心判断/摘要且正文 < 200 字")
    if issues:
        print(f"发现 {len(issues)} 个问题：")
        for issue in issues:
            print(f"  - {issue}")
        sys.exit(1)
    else:
        print(f"验证通过：{len(nodes)} 个节点，双链拓扑完整，内容均达标。")


def cmd_export(args):
    """导出概览：schema-agnostic 统计（不绑特定模板 section）。"""
    graph_dir = args.graph_dir
    nodes = get_all_nodes(graph_dir)
    if not nodes:
        print("图谱为空。")
        return

    output_path = os.path.join(graph_dir, '_overview.md')

    link_density = defaultdict(int)
    for name, node in nodes.items():
        for linked in node['links']:
            link_density[name] += 1
            link_density[linked] += 1

    # 关系提取（保留：从链接行解析关系类型）
    relations = []
    for name, node in nodes.items():
        for linked in node['links']:
            if linked in nodes:
                for line in node['content'].split('\n'):
                    if f"[[{linked}]]" in line:
                        rel_match = re.search(r'—\s*([^:\[]+?)(?::\s*(.+?))?\s*(?:\[来源)', line)
                        if rel_match:
                            rel_type = rel_match.group(1).strip()
                            rel_desc = rel_match.group(2).strip() if rel_match.group(2) else ''
                            relations.append((name, linked, rel_type, rel_desc))

    lines = [
        "# 知识图谱概览\n",
        "## 统计",
        f"- 概念节点总数: {len(nodes)}",
        f"- 关联关系总数: {sum(len(n['links']) for n in nodes.values()) // 2}",
        "",
        "## 核心概念 TOP 10（按关联密度排序）",
        "",
    ]

    sorted_by_density = sorted(link_density.items(), key=lambda x: x[1], reverse=True)
    for i, (name, count) in enumerate(sorted_by_density[:10], 1):
        node = nodes[name]
        # 摘要兼容两套模板：先 ## 摘要，再 ## 核心判断
        summary_match = (re.search(r'## 摘要\n(.+?)(?=\n##|\Z)', node['content'], re.DOTALL)
                         or re.search(r'## 核心判断\n(.+?)(?=\n##|\Z)', node['content'], re.DOTALL))
        summary = summary_match.group(1).strip().split('\n')[0] if summary_match else ''
        summary_short = summary[:60] + '...' if len(summary) > 60 else summary
        lines.append(f"{i}. [[{name}]] — 关联数: {count}")
        if summary_short:
            lines.append(f"   {summary_short}")

    if relations:
        lines.extend(["", "## 关联关系", "", "| 源概念 | 目标概念 | 关系类型 | 描述 |", "|--------|---------|---------|------|"])
        for source, target, rel_type, rel_desc in relations:
            lines.append(f"| [[{source}]] | [[{target}]] | {rel_type} | {rel_desc} |")

    # 内容丰富度（schema-agnostic：通用结构，不绑特定 section 名）
    lines.extend([
        "",
        "## 内容丰富度（schema-agnostic）",
        "",
        "| 概念 | section数 | 子节块数 | 表格行 | 双链 | 信度标记 |",
        "|------|----------|---------|--------|------|---------|",
    ])
    for name in sorted(nodes.keys()):
        content = nodes[name]['content']
        sections = len(re.findall(r'^## .+', content, re.MULTILINE))
        subblocks = len(re.findall(r'^### .+', content, re.MULTILINE))
        table_rows = len(re.findall(r'^\| .+\|.*\|\s*$', content, re.MULTILINE))
        links = len(nodes[name]['links'])
        confidence = len(re.findall(r'\[[A-E]\]', content))
        lines.append(f"| [[{name}]] | {sections} | {subblocks} | {table_rows} | {links} | {confidence} |")

    lines.extend(["", "## 全部概念节点", ""])
    for name in sorted(nodes.keys()):
        lines.append(f"- [[{name}]] ({len(nodes[name]['links'])} 个关联)")

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"知识图谱概览已导出: {output_path}")
    print(f"  节点数: {len(nodes)}")
    print(f"  核心概念: {', '.join(n for n, _ in sorted_by_density[:5])}")


def main():
    parser = argparse.ArgumentParser(description='知识图谱管理（v2 路B：link/verify/export，schema-agnostic）')
    parser.add_argument('-g', '--graph-dir', required=True, help='graph 目录路径')
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    p = subparsers.add_parser('link', help='建立双向链接')
    p.add_argument('source', help='源概念名称')
    p.add_argument('target', help='目标概念名称')
    p.add_argument('-t', '--relation', default='', help='关系类型')
    p.add_argument('--desc', default='', help='关系具体描述')
    p.add_argument('--source-file', default='', help='来源文件')

    subparsers.add_parser('verify', help='验证完整性（双链拓扑 + 内容）')
    subparsers.add_parser('export', help='导出概览（schema-agnostic）')

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    cmds = {'link': cmd_link, 'verify': cmd_verify, 'export': cmd_export}
    cmds[args.command](args)


if __name__ == '__main__':
    main()
