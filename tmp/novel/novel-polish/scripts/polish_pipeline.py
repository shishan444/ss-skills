#!/usr/bin/env python3
"""小说润色流水线 — Phase 2 批量处理脚本

用法:
    python3 polish_pipeline.py /path/to/stories/NN-书名/

功能:
    1. 清理反斜杠转义 (\" -> ")
    2. 清理行尾多余直引号
    3. 英文直引号 -> 中文弯引号 (按行内奇偶交替)
    4. 标准化省略号/破折号
    5. 输出统计 JSON

注意:
    - 弯引号用 \\u201c / \\u201d Unicode 转义，不要写字面量
      (部分写入工具会把字面弯引号归一化为 ASCII)
    - 运行后务必用 xxd 验证字节: sed -n '11p' chapter-01.md | xxd | head -3
    - 填充词清除见下方 FILLER_PATTERNS，清除后需人工复核对话行
"""
import os
import re
import json
import sys
from pathlib import Path

OPEN_Q = '\u201c'   # "
CLOSE_Q = '\u201d'  # "

FILLER_PATTERNS = [
    (re.compile(r'(也就是说|换句话说|简单来说|简而言之|总而言之)[，,——]+\s*'), ''),
    (re.compile(r'^(也就是说|换句话说|简单来说|简而言之|总而言之)[，,——]+\s*'), ''),
    (re.compile(r'说白了[，,就是]+\s*'), ''),
]

stats = {
    "files_processed": 0,
    "backslash_removed": 0,
    "trailing_dup_quotes_removed": 0,
    "straight_quotes_converted": 0,
    "ellipsis_normalized": 0,
    "emdashes_normalized": 0,
    "filler_removed_narration": 0,
    "filler_kept_dialogue": 0,
    "files_changed": 0,
}


def polish_text(text: str) -> str:
    local = {"backslash": 0, "trailing": 0, "quotes": 0,
             "ellipsis": 0, "emdash": 0, "filler_n": 0, "filler_d": 0}

    # 1. 反斜杠转义
    text, n = re.subn(r'\\"', '"', text)
    local["backslash"] += n
    text, n = re.subn(r"\\'", "'", text)
    local["backslash"] += n

    # 2. 行尾多余直引号
    def fix_trailing(m):
        local["trailing"] += len(m.group(0)) - 1
        return '"'
    text = re.sub(r'"{2,}$', fix_trailing, text, flags=re.MULTILINE)

    # 3. 省略号标准化
    text, n = re.subn(r'(?<!\.)\.{3}(?!\.)', '……', text)
    local["ellipsis"] += n
    text, n = re.subn(r'(?<!…)…(?!…)', '……', text)
    local["ellipsis"] += n

    # 4. 单 em-dash -> 双
    text, n = re.subn(r'(?<!—)—(?!—)', '——', text)
    local["emdash"] += n

    # 5. 直引号 -> 弯引号 (按行内奇偶交替)
    out_lines = []
    for line in text.split('\n'):
        result = []
        open_state = True
        for ch in line:
            if ch == '"':
                result.append(OPEN_Q if open_state else CLOSE_Q)
                open_state = not open_state
                local["quotes"] += 1
            else:
                result.append(ch)
        out_lines.append(''.join(result))
    text = '\n'.join(out_lines)

    # 6. 填充词清除 (对话行保留)
    new_lines = []
    for line in text.split('\n'):
        stripped = line.lstrip()
        is_dialogue = stripped.startswith(OPEN_Q)
        if is_dialogue:
            for pat, _ in FILLER_PATTERNS:
                if pat.search(line):
                    local["filler_d"] += 1
            new_lines.append(line)
            continue
        original = line
        for pat, repl in FILLER_PATTERNS:
            line = pat.sub(repl, line)
        if line != original:
            local["filler_n"] += 1
        new_lines.append(line)
    text = '\n'.join(new_lines)

    # 汇总
    stats["backslash_removed"] += local["backslash"]
    stats["trailing_dup_quotes_removed"] += local["trailing"]
    stats["straight_quotes_converted"] += local["quotes"]
    stats["ellipsis_normalized"] += local["ellipsis"]
    stats["emdashes_normalized"] += local["emdash"]
    stats["filler_removed_narration"] += local["filler_n"]
    stats["filler_kept_dialogue"] += local["filler_d"]
    return text


def merge_chapters(drafts_dir: Path, out_file: Path):
    files = sorted(drafts_dir.glob("chapter-*.md"),
                   key=lambda p: int(re.search(r'(\d+)', p.stem).group(1)))
    parts = [f"# 《{out_file.stem}》\n"]
    for i, f in enumerate(files):
        content = f.read_text(encoding='utf-8').rstrip()
        content = re.sub(r'^# (第.+章)', r'## \1', content, flags=re.MULTILINE)
        parts.append(content)
        if i < len(files) - 1:
            parts.append("\n\n---\n")
    out_file.write_text("\n".join(parts) + "\n", encoding='utf-8')
    return len(files), out_file.stat().st_size


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    drafts = root / "drafts"
    if not drafts.exists():
        print(f"错误：找不到 drafts/ 目录于 {drafts}")
        sys.exit(1)

    files = sorted(drafts.glob("chapter-*.md"),
                   key=lambda p: int(re.search(r'(\d+)', p.stem).group(1)))
    print(f"发现 {len(files)} 个章节文件")

    for f in files:
        original = f.read_text(encoding='utf-8')
        polished = polish_text(original)
        if polished != original:
            f.write_text(polished, encoding='utf-8')
            stats["files_changed"] += 1
        stats["files_processed"] += 1

    print(f"\n=== 润色统计 ===")
    for k, v in stats.items():
        if v > 0:
            print(f"  {k}: {v}")

    # 合并
    book_name = root.name.split('-', 1)[-1] if '-' in root.name else root.name
    out_file = root / f"{book_name}.md"
    n, size = merge_chapters(drafts, out_file)
    print(f"\n合并完成：{out_file} ({n} 章, {size:,} 字节)")

    # 保存统计
    (root / "_polish_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == "__main__":
    main()
