#!/usr/bin/env python3
import json
import locale
import os
import re
import sys

from dr_check import check_encoding, load_profile
from lang_config import get_lang_config, CHINESE_NUMERALS, LANG_CONFIG


# ── Source Extraction ─────────────────────────────────────────────────────

SOURCE_PATTERN = re.compile(r'[（(]([^）)]+?)[，,]\s*(\d{4})[）)]')


def extract_sources(filepath: str) -> dict:
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        content = f.read()
    matches = SOURCE_PATTERN.findall(content)
    seen = set()
    unique = []
    for inst, year in matches:
        key = inst.strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(key)
    return {
        "source_count": len(unique),
        "sources": unique,
        "sources_joined": "、".join(sorted(unique)),
        "total_mentions": len(matches),
    }


# ── TOC Generation ─────────────────────────────────────────────────────────


def _github_anchor(text: str) -> str:
    """Generate a GitHub-compatible heading anchor.
    
    Mirrors cmark-gfm + utf8proc: keep only Unicode letters (L), digits (N),
    spaces (Z), underscore (_), and hyphen (-). Drop all punctuation and symbols.
    """
    import unicodedata
    text = text.lower()
    result = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat.startswith(('L', 'N')) or ch in (' ', '_', '-'):
            result.append(ch)
    text = ''.join(result)
    text = re.sub(r'\s+', '-', text)
    text = re.sub(r'-+', '-', text)
    text = text.strip('-')
    return text


def generate_toc(outline_path: str) -> dict:
    with open(outline_path, 'r', encoding='utf-8-sig') as f:
        outline = json.load(f)
    chapters = outline.get('chapters', [])
    lang = outline.get('language', 'zh')
    cfg = get_lang_config(lang)
    lines = []
    for i, ch in enumerate(chapters):
        prefix = cfg['toc_prefix'](i + 1)
        title = ch.get('title', '')
        label = f"{prefix} {title}" if lang != 'zh' else f"{prefix}{title}"
        anchor = _github_anchor(label)
        lines.append(f"- [{label}](#{anchor})")
    return {
        "chapter_count": len(chapters),
        "toc_lines": lines,
        "toc_text": '\n'.join(lines),
    }


# ── Metadata Block Generation ─────────────────────────────────────────────


def generate_metadata(word_count: int, reading_time: int, data_until: str,
                       generate_time: str, depth_mode: str,
                       source_count: int, top_sources: list,
                       skill_version: str = "",
                       lang: str = "zh") -> dict:
    cfg = get_lang_config(lang)
    fields = cfg['metadata_fields']
    s = cfg['sep']
    fs = cfg['field_sep']
    version_str = f"{s}{fields[5]}{fs}{skill_version}" if skill_version else ""
    line1 = (
        f"> {cfg['metadata_label']}"
        f"{fields[0]}{fs}{word_count}"
        f"{s}{fields[1]}{fs}{reading_time} {cfg['minute_unit']}"
        f"{s}{fields[2]}{fs}{data_until}"
        f"{s}{fields[3]}{fs}{generate_time}"
        f"{s}{fields[4]}{fs}{depth_mode}{version_str}"
    )
    sorted_sources = sorted(top_sources)[:8]
    src_fmt = cfg['refs_count_format']
    count_text = src_fmt(source_count) if callable(src_fmt) else src_fmt.format(count=source_count)
    if lang == 'zh':
        source_str = "、".join(sorted_sources)
        line2 = f"> {cfg['references_label']}{source_str} 等 · {count_text}"
    else:
        source_str = ", ".join(sorted_sources)
        line2 = f"> {cfg['references_label']}{source_str} et al. · {count_text}"
    return {
        "metadata_line": line1,
        "source_line": line2,
        "full_block": line1 + '\n>\n' + line2,
    }


# ── Chapter Mapping ───────────────────────────────────────────────────────


def map_chapters(outline_path: str) -> dict:
    with open(outline_path, 'r', encoding='utf-8-sig') as f:
        outline = json.load(f)
    chapters = outline.get('chapters', [])
    mapping = {}
    for i, ch in enumerate(chapters):
        sqs = ch.get('sub_questions', [])
        chapter_num = i + 1
        mapping[chapter_num] = {
            "title": ch.get('title', ''),
            "sections": ch.get('sections', []),
            "sub_questions": [
                {
                    "id": sq.get('id', f"q{chapter_num}-{idx + 1}"),
                    "question": sq.get('question', ''),
                    "priority": sq.get('priority', 'medium'),
                }
                for idx, sq in enumerate(sqs)
                if isinstance(sq, dict)
            ],
            "sub_question_count": len(sqs),
        }
    return {"chapter_count": len(chapters), "mapping": mapping, "chapter_numbers": list(mapping.keys())}


# ── Hyperlinked Reference List ────────────────────────────────────────────


def generate_refs(datapool_path: str, numbered: bool = False, lang: str = "zh") -> dict:
    data = _read_json_handle_bom(datapool_path)
    records = data if isinstance(data, list) else [data]
    cfg = get_lang_config(lang)
    seen_keys = set()
    entries = []
    for rec in records:
        for fact in rec.get('facts') or []:
            url = (fact.get('url') or '').strip()
            local_path = (fact.get('local_path') or '').strip()
            inst = fact.get('src', '').strip()
            yr = fact.get('yr', '')
            title = fact.get('title', '').strip()
            locator = url or local_path
            if not locator or not inst:
                continue
            key = (inst, yr, locator)
            if key not in seen_keys:
                seen_keys.add(key)
                entries.append(
                    {
                        "publisher": inst,
                        "year": yr,
                        "title": title or inst,
                        "url": url,
                        "local_path": local_path,
                    }
                )

    src_fmt = cfg['refs_count_format']
    count_text = src_fmt(len(entries)) if callable(src_fmt) else src_fmt.format(count=len(entries))
    lines = [f"{cfg['refs_prefix']}\n", f"{count_text}\n"]
    if numbered:
        for i, entry in enumerate(entries, 1):
            inst = entry["publisher"]
            yr = entry["year"]
            title = entry["title"]
            label = f"{title} · {inst}" + (f" · {yr}" if yr else "")
            if entry["url"]:
                lines.append(f"({i}) [{label}]({entry['url']})")
            else:
                lines.append(
                    f"({i}) {label} · local:{os.path.basename(entry['local_path'])}"
                )
        ref_text = '\n'.join(lines[:2]) + '\n\n' + '\n\n'.join(lines[2:])
    else:
        for entry in entries:
            inst = entry["publisher"]
            yr = entry["year"]
            title = entry["title"]
            label = f"{title} · {inst}" + (f" · {yr}" if yr else "")
            if entry["url"]:
                lines.append(f"- [{label}]({entry['url']})")
            else:
                lines.append(f"- {label} · local:{os.path.basename(entry['local_path'])}")
        ref_text = '\n'.join(lines)
    return {"source_count": len(entries), "ref_lines": lines, "ref_text": ref_text}


# ── Convert Citations to Numeric Index ────────────────────────────────────

CITATION_RE = re.compile(r'[（(]([^）)]+?)[，,]\s*(\d{4})[）)]')

_UTF8_SIG = 'utf-8-sig'


def _read_json_handle_bom(path: str):
    with open(path, 'r', encoding=_UTF8_SIG) as f:
        return json.load(f)


def convert_citations(report_path: str, datapool_path: str, output_path: str = None, lang: str = "zh") -> dict:
    with open(report_path, 'r', encoding='utf-8-sig') as f:
        content = f.read()

    cfg = get_lang_config(lang)

    # Check: report should NOT contain （机构，年份） patterns
    legacy_cites = re.findall(r'[（(][^）)]+?[，,]\s*\d{4}[）)]', content)
    if legacy_cites:
        issues = [f"Found {len(legacy_cites)} legacy （机构，年份） citations — chapter agents must use (N) format"]
        return {"passed": False, "issues": issues, "changes": 0}

    # Load data-pool and build ref_map from first-appearance order
    data = _read_json_handle_bom(datapool_path)
    records = data if isinstance(data, list) else [data]

    seen = set()
    ordered_refs = []
    pool_map = {}
    for rec in records:
        for fact in rec.get('facts') or []:
            inst = fact.get('src', '').strip()
            yr = fact.get('yr', '')
            url = fact.get('url', '').strip()
            local_path = fact.get('local_path', '').strip()
            title = fact.get('title', '').strip()
            locator = url or local_path
            if not inst or not locator:
                continue
            key = (inst, yr, locator)
            if key not in seen:
                seen.add(key)
                ordered_refs.append(key)
            pool_map[key] = (title or inst, url, local_path)

    ref_map = {pair: i + 1 for i, pair in enumerate(ordered_refs)}

    # Scan body for [N] patterns
    split_marker = cfg['refs_prefix']
    body = content.split(split_marker)[0] if split_marker in content else content
    body_refs = set(re.findall(r'(?<!!)\[(\d+)\](?!\()', body))

    issues = []
    for num in sorted(body_refs, key=int):
        num_i = int(num)
        if num_i < 1 or num_i > len(ref_map):
            issues.append(f"Body references ({num}) which has no data-pool entry")

    # Build reference section
    entry_lines = []
    for key, num in sorted(ref_map.items(), key=lambda x: x[1]):
        inst, yr, locator = key
        title, url, local_path = pool_map.get(key, (inst, '', ''))
        label = title if title == inst else f"{title} · {inst}"
        label = label + (f" · {yr}" if yr else "")
        anchor = f'<a id="ref{num}"></a>'
        if url:
            entry_lines.append(f'{anchor}({num}) [{label}]({url})')
        else:
            entry_lines.append(
                f'{anchor}({num}) {label} · local:{os.path.basename(local_path)}'
            )

    ref_text = f'\n\n{cfg["refs_prefix"]}\n\n\n' + '\n\n'.join(entry_lines)

    # Insert/replace refs section
    old_section = re.search(rf'{cfg["refs_prefix"]}.*?(?=\n## |\Z)', content, re.DOTALL)
    if old_section:
        new_content = content[:old_section.start()] + ref_text + content[old_section.end():]
    else:
        new_content = content + ref_text

    # Validate: every [N] in body has matching ref anchor
    ref_anchors = set(re.findall(r'<a id="ref(\d+)"></a>', new_content))
    missing_in_refs = body_refs - ref_anchors
    orphan_anchors = ref_anchors - body_refs
    if missing_in_refs:
        issues.append(
            f"Citations without matching reference: [{', '.join(sorted(missing_in_refs, key=int))}]")

    # Convert [N] → [(N)](#refN)
    BODY_CITE_RE = re.compile(r'(?<!!)\[(\d+)\](?!\()')
    new_content = BODY_CITE_RE.sub(r'[(\1)](#ref\1)', new_content)

    # Clean up structural headings from other languages
    foreign_headings = set()
    for code, lcfg in LANG_CONFIG.items():
        if code == lang:
            continue
        foreign_headings.add(lcfg['refs_prefix'])
        foreign_headings.add(lcfg['disclaimer_title'])
        foreign_headings.add(lcfg['toc_heading'])
    for heading in foreign_headings:
        pattern = re.compile(
            rf'^{re.escape(heading)}\s*$.*?(?=\n## |\Z)',
            re.MULTILINE | re.DOTALL
        )
        new_content = pattern.sub('', new_content)

    # Write output
    output = output_path or report_path
    tmp = output + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(new_content)
    os.replace(tmp, output)

    return {
        "passed": len(issues) == 0,
        "changes": len(ref_map),
        "output": output,
        "issues": issues,
        "citation_count": len(body_refs),
        "ref_count": len(ref_anchors),
    }


# ── Encoding-safe stdin reader (cross-platform) ─────────────────────────────


def _read_stdin() -> str:
    raw = sys.stdin.buffer.read()
    if not raw:
        return ''
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode(locale.getpreferredencoding())
    except (UnicodeDecodeError, LookupError):
        pass
    return raw.decode('utf-8', errors='replace')


# ── JSON Write (atomic, encoding-safe) ─────────────────────────────────────


def write_json(filepath: str) -> dict:
    raw = _read_stdin()
    if not raw.strip():
        return {"passed": False, "issues": ["Empty input from stdin"]}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"passed": False, "issues": [f"JSON parse error: {e}"]}
    tmp = filepath + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
        os.replace(tmp, filepath)
    except (OSError, IOError) as e:
        return {"passed": False, "issues": [f"Write failed: {e}"]}
    return {"passed": True, "issues": [], "size": os.path.getsize(filepath)}


# ── Markdown Write (encoding-safe, Mojibake-free) ─────────────────────────


def write_md(filepath: str) -> dict:
    raw = _read_stdin()
    if not raw.strip():
        return {"passed": False, "issues": ["Empty input from stdin"]}
    tmp = filepath + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(raw)
        os.replace(tmp, filepath)
    except (OSError, IOError) as e:
        return {"passed": False, "issues": [f"Write failed: {e}"]}
    enc_check = check_encoding(filepath)
    if not enc_check['passed']:
        return {"passed": False, "issues": [f"Write succeeded but Mojibake detected: {enc_check['issues']}"]}
    return {"passed": True, "issues": [], "size": os.path.getsize(filepath)}


# ── Prepare Chapter Skeleton ──────────────────────────────────────────────


def prepare_chapter(outline_path: str, datapool_path: str,
                    chapter_num: int, total_chapters: int, mode: str) -> dict:
    with open(outline_path, 'r', encoding='utf-8-sig') as f:
        outline = json.load(f)
    with open(datapool_path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)

    chapters = outline.get('chapters', [])
    lang = outline.get('language', 'zh')
    cfg = get_lang_config(lang)

    if chapter_num < 1 or chapter_num > len(chapters):
        return {"passed": False, "issues": [f"Chapter {chapter_num} out of range (1-{len(chapters)})"]}

    ch = chapters[chapter_num - 1]
    title = ch.get('title', '')
    sections = ch.get('sections', [])
    sub_questions = ch.get('sub_questions', [])

    prof = load_profile(mode)
    total_limit = prof.get('max_chars', 3000)
    per_chapter_target = total_limit // max(total_chapters, 1)

    pool_records = data if isinstance(data, list) else [data]
    sq_questions = [
        sq.get('question', '') for sq in sub_questions if isinstance(sq, dict)
    ]
    sq_ids = {
        sq.get('id') for sq in sub_questions
        if isinstance(sq, dict) and sq.get('id')
    }

    ref_numbers = {}
    next_ref = 1
    for rec in pool_records:
        for fact in rec.get('facts') or []:
            key = (
                fact.get('src', ''),
                fact.get('yr', ''),
                fact.get('url', '') or fact.get('local_path', ''),
            )
            if key not in ref_numbers:
                ref_numbers[key] = next_ref
                next_ref += 1

    relevant_facts = []
    for rec in pool_records:
        rec_q = rec.get('question', '')
        id_match = rec.get('question_id') in sq_ids
        exact_match = rec_q in sq_questions
        match_score = sum(1 for sq in sq_questions if any(
            kw.lower() in rec_q.lower() for kw in sq.split() if len(kw) > 2
        ))
        if id_match or exact_match or match_score > 0:
            facts = rec.get('facts') or []
            for fact in facts:
                ref_key = (
                    fact.get('src', ''),
                    fact.get('yr', ''),
                    fact.get('url', '') or fact.get('local_path', ''),
                )
                relevant_facts.append({
                    "source": fact.get('src', ''),
                    "year": fact.get('yr', ''),
                    "metric": fact.get('met', ''),
                    "value": fact.get('val'),
                    "unit": fact.get('u', ''),
                    "context": fact.get('ctx', ''),
                    "confidence": fact.get('conf', ''),
                    "data_type": fact.get('data_type', ''),
                    "citation": ref_numbers.get(ref_key),
                })

    relevant_facts.sort(key=lambda x: x.get('year', ''), reverse=True)

    lines = []
    prefix_str = cfg['chapter_heading'](chapter_num, title)
    lines.append(f"# {title}")
    lines.append(f"\n> " + ("Core judgment for this chapter." if lang != 'zh' else "本章核心判断。") + "\n")
    per_section_est = per_chapter_target // max(len(sections), 1)
    char_note = "chars" if lang != 'zh' else "字"
    lines.append(f"> **{'Word target' if lang != 'zh' else '字数参考'}**：{'chapter target' if lang != 'zh' else '本章目标'} ≈ {per_chapter_target} {char_note}（{'per section' if lang != 'zh' else '每节'} ~{per_section_est} {char_note}）| sections: {len(sections)} | {'pre-matched facts' if lang != 'zh' else '预匹配事实'}: {len(relevant_facts)}\n")

    for idx, section in enumerate(sections):
        sec_num = idx + 1
        lines.append(f"### {chapter_num}.{sec_num} {section}\n")
        section_facts = [f for f in relevant_facts if section in f.get('context', '') or sec_num <= 2]
        if not section_facts:
            section_facts = relevant_facts[:2] if relevant_facts else []
            if section_facts:
                relevant_facts = relevant_facts[2:]
        for fact in section_facts[:3]:
            val_str = f"{fact['value']}{fact['unit']}" if fact['value'] is not None else fact['context']
            cite = f" [{fact['citation']}]" if fact.get('citation') else ""
            type_note = (
                f"；{fact['data_type']}/{fact['confidence']}"
                if fact.get('data_type') and fact.get('confidence')
                else ""
            )
            lines.append(
                f"- {fact['metric']}: {val_str}（{fact['source']}，"
                f"{fact['year']}{type_note}）{cite}"
            )
        lines.append("")

    skeleton = '\n'.join(lines)
    return {
        "passed": True,
        "skeleton": skeleton,
        "chapter_title": title,
        "fact_count": len(relevant_facts),
        "estimated_words": per_chapter_target,
    }


# ── Assemble Final Report ─────────────────────────────────────────────────


def assemble_report(outline_path: str, chapters_dir: str,
                    datapool_path: str,
                    mode: str, target_year: int,
                    wordcount_path: str = None,
                    output_path: str = None) -> dict:
    import datetime
    issues = []

    try:
        with open(outline_path, 'r', encoding='utf-8-sig') as f:
            outline = json.load(f)
    except Exception as e:
        return {"passed": False, "issues": [f"Failed to read outline: {e}"]}

    title = outline.get('title', '报告')
    lang = outline.get('language', 'zh')
    cfg = get_lang_config(lang)
    now = datetime.datetime.now()

    # Sanitize title for filesystem: replace Windows-invalid chars with '-'
    # Invalid on Windows: < > : " / \ | ? *
    safe_title = re.sub(r'[<>:"/\\|?*]', '-', title)
    # Also trim trailing dots/spaces (Windows issue)
    safe_title = safe_title.rstrip('. ')

    if not output_path:
        output_path = (
            f"works/research/{safe_title}-{now.strftime('%Y%m%d-%H%M%S')}/report.md"
        )
    elif os.path.isdir(output_path) or not output_path.endswith('.md'):
        base = os.path.join(output_path, f"{safe_title}-{now.strftime('%Y%m%d-%H%M%S')}.md")
        output_path = base
    chapters = outline.get('chapters', [])
    depth_mode = outline.get('mode', outline.get('depth_mode', mode))

    chapter_files = []
    for i in range(1, len(chapters) + 1):
        path = os.path.join(chapters_dir, f"chapter-{i}.md")
        if os.path.exists(path):
            chapter_files.append((i, path))
        else:
            issues.append(f"Missing chapter file: chapter-{i}.md")

    toc_result = generate_toc(outline_path)
    toc_text = toc_result['toc_text']

    chapter_texts = []
    for num, fpath in sorted(chapter_files):
        with open(fpath, 'r', encoding='utf-8-sig') as f:
            content = f.read().strip()
        content = re.sub(r'^#{1,2} .+?\n+', '', content, count=1)
        heading = cfg['chapter_heading'](num, chapters[num - 1].get('title', ''))
        chapter_texts.append(f'{heading}\n\n{content}')

    data_until = f"{target_year}" if lang != 'zh' else f"{target_year}年"
    generate_time = now.strftime("%Y-%m-%d %H:%M:%S")

    try:
        refs = generate_refs(datapool_path, numbered=True, lang=lang)
        total_sources = refs['source_count']
        ref_text = refs['ref_text']
    except Exception as e:
        total_sources = 0
        ref_text = f"{cfg['refs_prefix']}\n\n{'No source data' if lang != 'zh' else '无来源数据'}\n"
        issues.append(f"Source extraction failed: {e}")

    try:
        with open(datapool_path, 'r', encoding='utf-8-sig') as f:
            dp_data = json.load(f)
        records = dp_data if isinstance(dp_data, list) else [dp_data]
        source_freq = {}
        for rec in records:
            for fact in rec.get('facts') or []:
                src = fact.get('src', '')
                if src:
                    source_freq[src] = source_freq.get(src, 0) + 1
        top_sources = sorted(source_freq, key=source_freq.get, reverse=True)[:8]
    except Exception:
        top_sources = []

    version = ""

    temp_meta = generate_metadata(
        word_count=0, reading_time=1,
        data_until=data_until, generate_time=generate_time,
        depth_mode=depth_mode, source_count=total_sources,
        top_sources=top_sources, skill_version=version, lang=lang,
    )
    toc_heading = cfg['toc_heading']
    temp_parts = [
        f"# {title}\n",
        f"{temp_meta['full_block']}\n",
        toc_heading, "\n", toc_text, "\n",
    ]
    temp_parts.append('\n\n'.join(chapter_texts))
    temp_parts.append("\n\n---\n\n")
    temp_parts.append(ref_text)
    temp_parts.append(f"\n\n{cfg['disclaimer_title']}\n\n{cfg['disclaimer_text']}\n")
    temp_parts.append(f"\n{cfg['report_generated'].format(time=generate_time)}\n")
    full_report = '\n'.join(temp_parts)

    total_wc = len(re.sub(r'\s+', '', full_report))
    reading_time = max(1, round(total_wc / 800))

    meta = generate_metadata(
        word_count=total_wc, reading_time=reading_time,
        data_until=data_until, generate_time=generate_time,
        depth_mode=depth_mode, source_count=total_sources,
        top_sources=top_sources, skill_version=version, lang=lang,
    )
    report_parts = [
        f"# {title}\n",
        f"{meta['full_block']}\n",
        toc_heading, "\n", toc_text, "\n",
    ]
    report_parts.append('\n\n'.join(chapter_texts))
    report_parts.append("\n\n---\n\n")
    report_parts.append(ref_text)
    report_parts.append(f"\n\n{cfg['disclaimer_title']}\n\n{cfg['disclaimer_text']}\n")
    report_parts.append(f"\n{cfg['report_generated'].format(time=generate_time)}\n")
    full_report = '\n'.join(report_parts)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    tmp = output_path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(full_report)
        os.replace(tmp, output_path)
    except Exception as e:
        return {"passed": False, "issues": [f"Write failed: {e}"]}

    enc_check = check_encoding(output_path)
    if not enc_check['passed']:
        issues.append(f"Encoding issue in assembled report: {enc_check['issues']}")

    line_count = full_report.count('\n') + 1

    return {
        "passed": len(issues) == 0,
        "output_path": output_path,
        "line_count": line_count,
        "chapter_count": len(chapter_files),
        "word_count": total_wc,
        "issues": issues,
    }


# ── Confidence Assessment Section ────────────────────────────────────────

def generate_confidence_section(datapool_path: str, manifest_path: str,
                                lang: str = 'zh') -> dict:
    """Generate an evidence-quality summary from explicit ledger fields."""
    issues = []
    try:
        with open(datapool_path, 'r', encoding='utf-8-sig') as f:
            pool = json.load(f)
    except Exception as e:
        return {'passed': False, 'section': '',
                'issues': [f"Failed to read data-pool: {e}"]}

    try:
        with open(manifest_path, 'r', encoding='utf-8-sig') as f:
            manifest = json.load(f)
    except Exception as e:
        return {'passed': False, 'section': '',
                'issues': [f"Failed to read manifest: {e}"]}

    records = pool if isinstance(pool, list) else [pool]

    total_facts = 0
    conf_counts = {'high': 0, 'medium': 0, 'low': 0, 'unknown': 0}
    type_counts = {
        'actual': 0,
        'estimate': 0,
        'forecast': 0,
        'opinion': 0,
        'unknown': 0,
    }
    role_counts = {
        'primary': 0,
        'secondary': 0,
        'discovery': 0,
        'local': 0,
        'unknown': 0,
    }
    support_counts = {'direct': 0, 'indirect': 0, 'context': 0, 'unknown': 0}
    controversies_total = 0

    for rec in records:
        for fact in rec.get('facts') or []:
            total_facts += 1
            conf = (fact.get('conf') or '').strip().lower()
            dtype = (fact.get('data_type') or '').strip().lower()
            role = (fact.get('source_role') or '').strip().lower()
            support = (fact.get('support') or '').strip().lower()
            conf_counts[conf if conf in conf_counts else 'unknown'] += 1
            type_counts[dtype if dtype in type_counts else 'unknown'] += 1
            role_counts[role if role in role_counts else 'unknown'] += 1
            support_counts[support if support in support_counts else 'unknown'] += 1
            controversies_total += len(fact.get('contradicts') or [])
        controversies_total += len(rec.get('controversies') or [])

    coverage_raw = manifest.get('coverage') or {}
    if isinstance(coverage_raw, dict):
        adequate = int(coverage_raw.get('supported', 0))
        insufficient = int(coverage_raw.get('insufficient', 0))
        total_subq = int(coverage_raw.get('total_questions', adequate + insufficient))
        coverage_ratio = float(
            coverage_raw.get(
                'ratio',
                adequate / total_subq if total_subq else 0,
            )
        )
    else:
        adequate = sum(
            1 for item in coverage_raw
            if item.get('status') in ('adequate', 'supported')
        )
        insufficient = sum(
            1 for item in coverage_raw if item.get('status') == 'insufficient'
        )
        total_subq = len(coverage_raw)
        coverage_ratio = adequate / total_subq if total_subq else 0
    data_limited = manifest.get('data_limited', False)

    cfg = get_lang_config(lang)
    heading = cfg.get('confidence_heading', '## Confidence Assessment')
    lines = [heading, '']

    primary = role_counts['primary']
    secondary = role_counts['secondary']
    discovery = role_counts['discovery']
    local = role_counts['local']
    label_src = '来源角色' if lang == 'zh' else 'Source Roles'
    lines.append(
        f"**{label_src}**："
        f"{'一手' if lang == 'zh' else 'Primary'} {primary}条 · "
        f"{'二手' if lang == 'zh' else 'Secondary'} {secondary}条 · "
        f"{'发现型' if lang == 'zh' else 'Discovery'} {discovery}条 · "
        f"{'本地资料' if lang == 'zh' else 'Local'} {local}条"
    )
    lines.append('')

    act = type_counts['actual']
    est = type_counts['estimate']
    fct = type_counts['forecast']
    opinion = type_counts['opinion']
    if total_facts > 0:
        act_pct = round(act / total_facts * 100)
        est_pct = round(est / total_facts * 100)
        fct_pct = round(fct / total_facts * 100)
        opinion_pct = round(opinion / total_facts * 100)
    else:
        act_pct = est_pct = fct_pct = opinion_pct = 0
    label_actual = '已公布' if lang == 'zh' else 'Actual'
    label_est = '估算' if lang == 'zh' else 'Estimate'
    label_fcst = '预测' if lang == 'zh' else 'Forecast'
    label_opinion = '观点' if lang == 'zh' else 'Opinion'
    lines.append(f"**{'数据类型' if lang == 'zh' else 'Data Type'}**："
                 f"{label_actual} {act}条({act_pct}%) · "
                 f"{label_est} {est}条({est_pct}%) · "
                 f"{label_fcst} {fct}条({fct_pct}%) · "
                 f"{label_opinion} {opinion}条({opinion_pct}%)")
    lines.append('')

    high = conf_counts['high']
    medium = conf_counts['medium']
    low = conf_counts['low']
    if total_facts > 0:
        high_pct = round(high / total_facts * 100)
        medium_pct = round(medium / total_facts * 100)
        low_pct = round(low / total_facts * 100)
    else:
        high_pct = medium_pct = low_pct = 0
    label_high = '高置信' if lang == 'zh' else 'High'
    label_med = '中等' if lang == 'zh' else 'Medium'
    label_low = '低置信' if lang == 'zh' else 'Low'
    lines.append(f"**{'置信度分布' if lang == 'zh' else 'Confidence Distribution'}**："
                 f"{label_high} {high}条({high_pct}%) · "
                 f"{label_med} {medium}条({medium_pct}%) · "
                 f"{label_low} {low}条({low_pct}%)")
    lines.append('')

    if total_subq > 0:
        label_adequate = '已覆盖' if lang == 'zh' else 'Supported'
        label_insuff = '不足' if lang == 'zh' else 'Insufficient'
        lines.append(f"**{'覆盖度' if lang == 'zh' else 'Coverage'}**："
                     f"{total_subq}{'个子问题中 ' if lang == 'zh' else ' sub-questions — '}"
                     f"{adequate} {label_adequate}、{insufficient} {label_insuff}")
        lines.append('')

    if data_limited:
        label_limited = '有（部分子问题数据覆盖不足，结论需谨慎参考）' if lang == 'zh' else 'Yes (some sub-questions have insufficient coverage — conclusions should be treated with caution)'
    else:
        label_limited = '无' if lang == 'zh' else 'None'
    lines.append(f"**{'数据限制' if lang == 'zh' else 'Data Limitations'}**：{label_limited}")
    lines.append('')

    if controversies_total > 0:
        label_cont = '存在' if lang == 'zh' else ''
        label_cont2 = '处跨源数据差异，已在正文对应章节并排呈现' if lang == 'zh' else ' instances of cross-source data discrepancies, presented side-by-side in relevant chapters'
        lines.append(f"**{'跨源矛盾' if lang == 'zh' else 'Cross-source Discrepancies'}**："
                     f"{label_cont}{controversies_total}{label_cont2}")
        lines.append('')

    if total_facts > 0:
        confidence_component = (
            high + medium * 0.6 + low * 0.2
        ) / total_facts * 35
        role_component = (
            primary + secondary * 0.75 + local * 0.6 + discovery * 0.2
        ) / total_facts * 20
        support_component = (
            support_counts['direct']
            + support_counts['indirect'] * 0.6
            + support_counts['context'] * 0.3
        ) / total_facts * 15
        score = confidence_component + role_component + support_component
        score += coverage_ratio * 20
        score += 0 if data_limited else 10
        score = round(score)

        if score >= 75:
            label_verdict = '结论可靠' if lang == 'zh' else 'Reliable'
        elif score >= 50:
            label_verdict = '基本可信' if lang == 'zh' else 'Moderate'
        else:
            label_verdict = '谨慎参考' if lang == 'zh' else 'Caution'

        rating_label = '证据质量评级' if lang == 'zh' else 'Evidence Quality Rating'
        lines.append(f"**{rating_label}**：{label_verdict}（{score}/100）")
        note = (
            '该分数是字段完备度、来源角色、直接支持与问题覆盖的启发式汇总，不是统计概率。'
            if lang == 'zh'
            else 'This score is a heuristic summary of explicit evidence fields, not a statistical probability.'
        )
        lines.append(note)
        lines.append('')

    else:
        score = 0
        label_verdict = '无数据' if lang == 'zh' else 'No data'

    section = '\n'.join(lines)

    coverage_summary = manifest.get(
        'coverage_summary',
        f"{adequate}/{total_subq}" if total_subq else 'unknown',
    )
    adequate_subq = adequate
    total_subq_count = total_subq
    summary = {
        'coverage': coverage_summary,
        'total_facts': total_facts,
        'high_pct': high_pct if total_facts > 0 else 0,
        'medium_pct': medium_pct if total_facts > 0 else 0,
        'low_pct': low_pct if total_facts > 0 else 0,
        'actual_pct': act_pct if total_facts > 0 else 0,
        'est_pct': est_pct if total_facts > 0 else 0,
        'fct_pct': fct_pct if total_facts > 0 else 0,
        'opinion_pct': opinion_pct if total_facts > 0 else 0,
        'primary_pct': round(primary / total_facts * 100) if total_facts > 0 else 0,
        'data_limited': data_limited,
        'controversies': controversies_total,
        'adequate_subq': adequate_subq,
        'total_subq': total_subq_count,
        'verdict_label': label_verdict if total_facts > 0 else ('无数据' if lang == 'zh' else 'No data'),
        'score': score,
    }
    return {'passed': True, 'section': section, 'issues': issues, 'summary': summary}


def escape_currency(report_path: str) -> dict:
    """Escape unescaped dollar signs to prevent LaTeX math mode rendering.

    Platforms like Zhihu, Typora, Obsidian and GitHub with MathJax interpret
    $ as inline math delimiter. This function escapes standalone $ used as
    currency prefix, while skipping protected contexts.
    """
    with open(report_path, 'r', encoding='utf-8-sig') as f:
        content = f.read()

    changes = 0
    protected = {}
    counter = [0]

    def _protect(pattern, template='__DOLLAR_SAFE_{}__', flags=0):
        nonlocal content
        def replacer(m):
            counter[0] += 1
            key = template.format(counter[0])
            protected[key] = m.group(0)
            return key
        content = re.sub(pattern, replacer, content, flags=flags)

    # Protect contexts where $ should NOT be escaped
    _protect(r'```.*?```', '__CODE_BLOCK_{}__', re.DOTALL)  # fenced code blocks
    _protect(r'`[^`]+`', '__INLINE_CODE_{}__')             # inline code
    _protect(r'\[([^\[\]]*)\]\(([^)]*)\)', '__MD_LINK_{}__')  # markdown links (before URLs)
    _protect(r'https?://[^\s\)]+', '__URL_{}__')            # bare URLs
    _protect(r'<[^>]+>', '__HTML_TAG_{}__')                 # HTML tags (anchors etc.)
    _protect(r'^\|[-:]+\|', '__TABLE_SEP_{}__', re.MULTILINE)  # table separators

    # Strategy: escape ALL $ that are followed by a digit (currency pattern)
    # while skipping those already escaped (\$)
    def _escape_dollar(m):
        nonlocal changes
        changes += 1
        return m.group(1) + '\\' + m.group(2)

    # Match $ that is NOT preceded by backslash, and IS followed by a digit
    content = re.sub(r'(^|[^\\])(\$)(?=\d)', _escape_dollar, content)

    # Restore protected segments in reverse insertion order so markdown links
    # restored after URL placeholders still get their URLs expanded.
    for key, val in reversed(list(protected.items())):
        content = content.replace(key, val)

    issues = []
    if re.search(r'\]\(__URL_\d+__\)', content):
        issues.append('Unresolved __URL_N__ placeholders in markdown links')

    # Write back
    tmp = report_path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)
    os.replace(tmp, report_path)

    return {'passed': len(issues) == 0, 'issues': issues, 'changes': changes}
