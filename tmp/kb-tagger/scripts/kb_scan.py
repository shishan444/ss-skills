#!/usr/bin/env python3
"""扫描知识库目录下所有 .md 文件的 frontmatter，输出文本摘要。

仅为 kb-tagger link 模式服务。
输出格式为纯文本，便于 LLM 作为参考资料。
"""

import sys
import os
import re


def extract_frontmatter(content):
    """提取 YAML frontmatter 内容。"""
    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return None
    return match.group(1)


def parse_frontmatter(fm_text):
    """解析 frontmatter 为字典。"""
    result = {}
    current_key = None
    current_list = []

    for line in fm_text.split('\n'):
        stripped = line.strip()

        if stripped.startswith('#'):
            continue

        if stripped.startswith('- ') and current_key:
            current_list.append(stripped[2:].strip().strip('"').strip("'"))
            continue

        if current_key and current_list:
            result[current_key] = current_list
            current_list = []
        elif current_key and not current_list:
            result[current_key] = ''

        if ':' in stripped and not stripped.startswith('- '):
            key, _, value = stripped.partition(':')
            key = key.strip()
            value = value.strip()

            if value.startswith('[') and value.endswith(']'):
                inner = value[1:-1].strip()
                if inner:
                    result[key] = [
                        item.strip().strip('"').strip("'")
                        for item in inner.split(',')
                    ]
                else:
                    result[key] = []
                current_key = None
            elif value:
                result[key] = value.strip('"').strip("'")
                current_key = None
            else:
                current_key = key
                current_list = []

    if current_key and current_list:
        result[current_key] = current_list
    elif current_key:
        result[current_key] = current_list if current_list else ''

    return result


def format_list(val):
    """格式化列表值为显示文本。"""
    if isinstance(val, list):
        return '[' + ', '.join(str(v) for v in val) + ']'
    return str(val)


def scan_directory(directory):
    """扫描目录下所有 .md 文件，输出文本摘要。"""
    lines = []
    count = 0

    for root, dirs, files in os.walk(directory):
        dirs[:] = sorted(dirs)
        for fname in sorted(files):
            if not fname.endswith('.md'):
                continue

            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                lines.append(f"[{fname}] 读取失败: {e}")
                lines.append("")
                continue

            fm_text = extract_frontmatter(content)
            if fm_text is None:
                continue

            fm = parse_frontmatter(fm_text)
            if not fm:
                continue

            count += 1
            lines.append(f"[{fname}]")

            # anchor
            if 'anchor' in fm and fm['anchor']:
                lines.append(f"  anchor: {fm['anchor']}")

            # tags / leads / aliases
            for field in ['tags', 'leads', 'aliases']:
                if field in fm and fm[field]:
                    lines.append(f"  {field}: {format_list(fm[field])}")

            # connections
            has_connections = False
            for field in ['support', 'resonate', 'tension', 'instance']:
                if field in fm and fm[field]:
                    if not has_connections:
                        lines.append("  connections:")
                        has_connections = True
                    if isinstance(fm[field], list):
                        for item in fm[field]:
                            lines.append(f"    {field}: {item}")
                    else:
                        lines.append(f"    {field}: {fm[field]}")

            lines.append("")

    lines.insert(0, "=== 笔记索引 ===")
    lines.insert(1, "")
    lines.append(f"--- 共 {count} 篇笔记 ---")

    return '\n'.join(lines)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python kb_scan.py <知识库目录>")
        sys.exit(1)

    directory = sys.argv[1]
    if not os.path.isdir(directory):
        print(f"错误: {directory} 不是有效目录")
        sys.exit(1)

    print(scan_directory(directory))
