"""Shared final contract for ordinary assembly and evaluation consumers."""
from __future__ import annotations

from collections import Counter
import re

from core.domain.markdown.models import PageMarkdownDTO
from core.domain.markdown.protocol import TABLE_REFERENCE_RE, PROTOCOL_VERSION
from core.services.page_failures import page_failures, record_page_failure, failure_markdown
from core.services.structured_markdown_restore import restore_structured_markdown


def unresolved_references(text: str, literal_references=()) -> list[str]:
    literals = Counter(literal_references)
    unresolved = []
    for match in TABLE_REFERENCE_RE.finditer(text):
        token = match.group()
        if literals[token]:
            literals[token] -= 1
        else:
            unresolved.append(token)
    return unresolved


def validate_page_markdown(page: PageMarkdownDTO) -> str:
    # Registry-only validation reuses the pure restoration contract, without
    # applying its reconstructed text during final validation.
    check = restore_structured_markdown('', page.structured_blocks, context=page.restore_context)
    for issue in check.issues:
        if issue.severity == 'error':
            record_page_failure(page.page, 'markdown_validation', issue.code)
    remaining = unresolved_references(page.markdown, page.restore_context.literal_references)
    if remaining:
        record_page_failure(page.page, 'markdown_validation', 'unresolved_table_reference')
    known = {b.placeholder: b for b in page.structured_blocks if b.placeholder.startswith('[[TABLE_BLOCK:')}
    available = Counter({b.rendered_text.strip(): page.markdown.count(b.rendered_text.strip()) for b in known.values() if b.rendered_text.strip()})
    for block in known.values():
        rendered = block.rendered_text.strip()
        if rendered and available[rendered]:
            available[rendered] -= 1
        elif rendered:
            record_page_failure(page.page, 'markdown_validation', 'missing_rendered_table')
    for failure in page.failures:
        record_page_failure(page.page, failure.stage, failure.reason)
    page.failures = page_failures(page.page)
    usable = re.sub(r'(?m)^\s*(?:@page:.*|\[Error\].*)$', '', page.markdown).strip()
    state = 'complete_with_errors' if page.failures and usable else ('failed' if page.failures or not usable else 'complete')
    page.page.metadata['result_status'] = state
    page.page.metadata['structured_markdown_protocol'] = PROTOCOL_VERSION
    page.page.metadata['structured_literal_references'] = list(page.restore_context.literal_references)
    for failure in page.failures:
        marker = failure.render_markdown()
        if marker not in page.markdown:
            page.markdown = page.markdown.rstrip() + '\n\n' + marker
    return state


def document_result_status(document) -> str:
    """Guard final writers too, including output paths that bypass assembly."""
    literals = [r for page in document.pages for r in page.metadata.get('structured_literal_references', [])]
    remaining = unresolved_references(document.markdown or '', literals)
    failures = any(page_failures(page) or page.metadata.get('result_status') in {'failed', 'complete_with_errors'} for page in document.pages)
    for page in document.pages if document.markdown else ():
        for failure in page_failures(page):
            marker = failure.render_markdown()
            if marker not in (document.markdown or ''):
                document.markdown = (document.markdown or '').rstrip() + '\n\n' + marker
    if remaining:
        failures = True
        marker = '[Error] markdown_validation: unresolved_table_reference'
        if marker not in (document.markdown or ''):
            document.markdown = (document.markdown or '').rstrip() + '\n\n' + marker
        for page in document.pages:
            page.metadata['result_status'] = 'complete_with_errors'
    usable = re.sub(r'(?m)^\s*(?:@page:.*|\[Error\].*)$', '', document.markdown or '').strip()
    if not usable:
        return 'failed'
    return 'complete_with_errors' if failures else 'complete'


def require_complete_document(document) -> None:
    if document_result_status(document) != 'complete':
        raise ValueError('document has final Markdown contract errors')
