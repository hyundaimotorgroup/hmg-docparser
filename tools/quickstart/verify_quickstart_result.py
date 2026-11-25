#!/usr/bin/env python3
"""Reject incomplete quickstart runs using actual page routing and provider usage."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

import pdfplumber
from pypdf import PdfReader
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from core.services.pdf_rendering import pdf_has_images


def records(path):
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def verify(config, evidence):
    output = Path(config['output_dir'])
    fixture = Path(config['input_dir'])
    markdown = output / f'{fixture.stem}.md'
    errors = []
    text = markdown.read_text(encoding='utf-8') if markdown.is_file() else ''
    expected = list(range(1, len(PdfReader(fixture).pages) + 1))
    markers = [int(n) for n in re.findall(r'(?m)^@page:(\d+)\s*$', text)]
    if markers != expected:
        errors.append('final page markers missing, duplicated or out of order')
    if not text.strip() or '[Error]' in text:
        errors.append('final Markdown missing, empty or contains page failure markers')
    job = output / '_llm_usage_summary.json'
    summary = json.loads(job.read_text()) if job.is_file() else {}
    if summary.get('result_status') != 'complete':
        errors.append('pipeline result_status is not complete')
    nodes = config['pipeline']['nodes']
    enabled = {node['id']: node for node in nodes if node.get('node_config', {}).get('enabled', True)}
    stage1 = [n for n in enabled.values() if n['node'] == 'stage1_page_router']
    stage2 = [n for n in enabled.values() if n['node'] == 'stage2_element_router']
    s1 = records(output / 'stage1_report.jsonl')
    s2 = records(output / 'stage2_report.jsonl')
    usage = records(output / '_llm_usage.jsonl')
    by_page = {}
    for row in usage:
        meta = row.get('metadata', {})
        page = meta.get('page_no')
        if page is None and type(meta.get('page_index')) is int:
            page = meta['page_index'] + 1
        if page not in expected:
            errors.append('model usage lacks a valid page attribution')
        node_id = re.sub(r'#p\d+$', '', str(meta.get('node_id', '')))
        by_page.setdefault(page, []).append((node_id, row))

    if stage1:
        if Counter(r.get('page_no') for r in s1) != Counter(expected):
            errors.append('Stage 1 evidence missing or duplicated')
        if any(r.get('status') != 'ok' or r.get('stage1_level') not in {1, 2} for r in s1):
            errors.append('Stage 1 inference failed or returned invalid levels')
    if stage2:
        if Counter(r.get('page_no') for r in s2) != Counter(expected):
            errors.append('Stage 2 page evidence missing or duplicated')
        if any(r.get('status') != 'ok' or any(b.get('stage2_level') not in {1, 2, 3} for b in r.get('blocks', [])) for r in s2):
            errors.append('required Stage 2 elements were not successfully classified')
    # Each required table/image VLM element needs a successful actual provider
    # response; Stage 2 health or classifications alone are insufficient.
    for row in s2:
        for block in row.get('blocks', []):
            level = block.get('stage2_level')
            if type(level) is not int or level < 2:
                continue
            label = (block.get('label') or '').lower()
            model_type = ('table_vlm_caption_maker' if label in {'table', 'tab'}
                          else 'image_vlm_processor')
            candidates = [n for n in enabled.values() if n['node'] == model_type
                          and n.get('node_config', {}).get('use_vlm_parse', True)]
            if candidates and not any(
                node_id in {n['id'] for n in candidates}
                and record.get('metadata', {}).get('block_id') == block.get('block_id')
                and record.get('metadata', {}).get('processing_outcome') == 'success'
                for node_id, record in by_page.get(row.get('page_no'), [])
            ):
                errors.append(f'required element VLM response missing on page {row.get("page_no")}')
    sections = dict(zip(markers, re.split(r'(?m)^@page:\d+\s*$', text)[1:]))
    pages = []
    with pdfplumber.open(fixture) as pdf:
        for row in s1:
            number = row.get('page_no')
            if number not in expected:
                continue
            image = pdf_has_images(fixture, page_index=number - 1)
            native = str(pdf.pages[number - 1].extract_text() or '').strip()
            calls = Counter(n for n, _ in by_page.get(number, []))
            l1 = row.get('stage1_level') == 1
            gate = l1 and not image and bool(native)
            whole = sum(c for n, c in calls.items() if n.startswith('whole_page_llm'))
            global_calls = sum(c for n, c in calls.items() if n.startswith('global_context_page'))
            successful = Counter(n for n, record in by_page.get(number, [])
                                 if record.get('metadata', {}).get('processing_outcome') == 'success')
            if l1 and not gate and not successful.get('whole_page_llm'):
                errors.append(f'L1 whole-page successful response missing on page {number}')
            if not l1 and any(n['node'] == 'global_context_extraction_vlm_merger' for n in enabled.values()) and not successful.get('global_context_page'):
                errors.append(f'L2 global-context successful response missing on page {number}')
            if l1 and global_calls:
                errors.append(f'L1 global-context request on page {number}')
            if gate and whole:
                errors.append(f'native L1 whole-page request on page {number}')
            if l1 and not gate and whole == 0:
                errors.append(f'L1 whole-page usage missing on page {number}')
            if not l1 and any(n['node'] == 'global_context_extraction_vlm_merger' for n in enabled.values()) and global_calls == 0:
                errors.append(f'L2 global-context usage missing on page {number}')
            preserved = not gate or re.sub(r'\s+', '', native) in re.sub(r'\s+', '', sections.get(number, ''))
            if not preserved:
                errors.append(f'native L1 text lost on page {number}')
            pages.append({'page_no': number, 'stage1_level': row.get('stage1_level'),
                          'raster_image': image, 'native_text_direct': gate,
                          'native_text_preserved': preserved if gate else None,
                          'model_requests': dict(calls)})
    result = {'status': 'failed' if errors else 'complete', 'errors': sorted(set(errors)),
              'final_markdown': str(markdown), 'page_count': len(expected),
              'page_markers': markers, 'router_enabled': bool(stage1 or stage2),
              'stage1_records': len(s1), 'stage2_records': len(s2),
              'stage2_classified_blocks': sum(len(r.get('blocks', [])) for r in s2),
              'model_requests': len(usage),
              'failed_model_attempts': sum(r.get('metadata', {}).get('processing_outcome') != 'success' for r in usage),
              'pages': sorted(pages, key=lambda r: r['page_no'])}
    if markdown.is_file():
        result.update(bytes=markdown.stat().st_size, sha256=hashlib.sha256(markdown.read_bytes()).hexdigest())
    Path(evidence, 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    if errors:
        raise ValueError('; '.join(sorted(set(errors))))
    return result


if __name__ == '__main__':
    try:
        result = verify(yaml.safe_load(Path(sys.argv[1]).read_text()), Path(sys.argv[2]))
        print(f'SUCCESS: {result["page_count"]} pages, {result["model_requests"]} model requests; routing and final output verified')
    except (ValueError, OSError, KeyError) as exc:
        raise SystemExit(f'ERROR: {exc}') from None
