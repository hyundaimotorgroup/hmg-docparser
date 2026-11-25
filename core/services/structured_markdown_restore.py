"""Pure table restoration plus an explicit compatibility/diagnostic boundary."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
from typing import TYPE_CHECKING

from core.domain.markdown.models import StructuredMarkdownBlockDTO, StructuredRestoreContext
from core.domain.markdown.protocol import PROTOCOL_VERSION, TABLE_REFERENCE_RE

if TYPE_CHECKING:
    from core.domain.document.models import PageDTO


@dataclass(frozen=True, slots=True)
class RestoreIssue:
    code: str
    severity: str
    placeholder: str
    occurrence: str


@dataclass(slots=True)
class StructuredRestoreResult:
    text: str
    issues: list[RestoreIssue] = field(default_factory=list)
    restored_ids: list[str] = field(default_factory=list)
    appended_ids: list[str] = field(default_factory=list)
    removed_references: list[str] = field(default_factory=list)


def restore_structured_markdown(
    text: str,
    structured_blocks: list[StructuredMarkdownBlockDTO],
    *,
    context: StructuredRestoreContext | None = None,
) -> StructuredRestoreResult:
    """Restore every occurrence, preserving uncertain references and surrounding text."""
    context = context or StructuredRestoreContext()
    result = StructuredRestoreResult(text)
    known: dict[str, StructuredMarkdownBlockDTO] = {}
    conflicts = set()
    for block in structured_blocks:
        token = block.placeholder
        if not token.startswith('[[TABLE_BLOCK:'):
            continue
        if token in known and (known[token].rendered_text, known[token].render_format) != (block.rendered_text, block.render_format):
            conflicts.add(token)
        else:
            known[token] = block

    def issue(code, token, occurrence, severity='error'):
        result.issues.append(RestoreIssue(code, severity, token, occurrence))

    if context.registry_status == 'incomplete':
        issue('incomplete_structured_registry', '', 'registry')
    unsafe = set()
    from core.services.markdown_safety import sanitize_output_markdown
    for token, block in known.items():
        if block.render_format.value == "html" and sanitize_output_markdown(block.rendered_text.strip()) != block.rendered_text.strip():
            unsafe.add(token)
            issue("unsafe_rendered_table", token, "registry")

    for token in sorted(conflicts):
        issue('conflicting_structured_block', token, 'registry')
    for token in context.supplied_references:
        if token not in known:
            issue('missing_structured_block', token, 'registry')
    literals = Counter(context.literal_references)
    referenced = set()
    pieces = []
    end = 0
    for match in TABLE_REFERENCE_RE.finditer(text):
        if match.start() < end:
            continue
        token = match.group()
        occurrence = f'{match.start()}:{match.end()}'
        replacement = token
        stop = match.end()
        if literals[token]:
            literals[token] -= 1
        elif not token.endswith(']]') or token == '[[TABLE_BLOCK:]]':
            issue('malformed_table_reference', token, occurrence)
        elif token in conflicts or token in unsafe:
            referenced.add(token)
        elif token in known:
            referenced.add(token)
            block = known[token]
            rendered = (block.rendered_text or '').strip()
            if not rendered:
                issue('empty_rendered_table', token, occurrence)
            else:
                replacement = rendered
                result.restored_ids.append(token)
                summary = (block.summary or '').strip()
                if summary and text[stop:].startswith('\n' + summary):
                    boundary = stop + 1 + len(summary)
                    if boundary == len(text) or text[boundary] in '\r\n':
                        stop = boundary
        elif token in context.supplied_references:
            issue('missing_structured_block', token, occurrence)
        elif context.registry_status == 'complete':
            replacement = ''
            result.removed_references.append(token)
            issue('invented_table_reference', token, occurrence, 'warning')
        else:
            issue('unresolved_table_reference', token, occurrence)
        pieces.extend((text[end:match.start()], replacement))
        end = stop
    pieces.append(text[end:])
    result.text = ''.join(pieces)

    # Consume exact existing occurrences per identity. Equal tables from different
    # actual blocks need separate occurrences; explicit repeated references survive.
    available = Counter({b.rendered_text.strip(): text.count(b.rendered_text.strip()) for b in known.values() if b.rendered_text.strip()})
    appended = []
    ordered = sorted(known.items(), key=lambda item: (item[1].reading_order is None, item[1].reading_order or 0, item[0]))
    for token, block in ordered:
        if token in conflicts or token in unsafe or token in referenced:
            continue
        rendered = (block.rendered_text or '').strip()
        if not rendered:
            issue('empty_rendered_table', token, 'registry')
        elif available[rendered]:
            available[rendered] -= 1
        else:
            appended.append(rendered)
            result.appended_ids.append(token)
    if appended:
        result.text = '\n\n'.join([result.text.rstrip(), *appended]).strip()
    return result


def record_restore_result(
    result: StructuredRestoreResult,
    structured_blocks: list[StructuredMarkdownBlockDTO],
    *,
    page: 'PageDTO | None' = None,
    recovery_dir: str | Path | None = None,
    channel: str = 'body',
) -> None:
    """Accumulate body/debug diagnostics; persistence never changes restoration."""
    if page is not None:
        page.metadata['structured_markdown_protocol'] = PROTOCOL_VERSION
        entries = page.metadata.setdefault('structured_restore_issues', [])
        for item in result.issues:
            entry = {**asdict(item), 'channel': channel}
            if entry not in entries:
                entries.append(entry)
        if channel == 'body':
            from core.services.page_failures import record_page_failure
            for item in result.issues:
                if item.severity == 'error':
                    record_page_failure(page, 'structured_restore', item.code)
        identities = page.metadata.setdefault('structured_restore_identities', {})
        previous = identities.setdefault(channel, {'restored_ids': [], 'appended_ids': [], 'removed_references': []})
        for key in previous:
            previous[key] = list(dict.fromkeys([*previous[key], *getattr(result, key)]))
    if recovery_dir is None or not result.issues:
        return
    try:
        destination = Path(recovery_dir)
        destination.mkdir(parents=True, exist_ok=True)
        document_id = page.document_id if page else 'document'
        page_no = page.page_no if page else 0
        path = destination / f'{_safe_name(document_id)}_page_{page_no}_structured_recovery.json'
        payload = json.loads(path.read_text()) if path.exists() else {'document_id': document_id, 'page_no': page_no, 'channels': {}}
        previous = payload['channels'].get(channel, {})
        issues = previous.get('issues', [])
        for item in result.issues:
            if asdict(item) not in issues:
                issues.append(asdict(item))
        payload['channels'][channel] = {'text': result.text, 'issues': issues}
        # Preserve the legacy recovery fields for existing private consumers.
        payload['unresolved'] = [{'placeholder': i['placeholder'], 'reason': i['code']} for c in payload['channels'].values() for i in c['issues'] if i['severity'] == 'error']
        payload['structured_blocks'] = [asdict(b) for b in structured_blocks]
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(path)
        if page is not None:
            page.metadata['structured_restore_recovery_artifact'] = str(path)
    except (OSError, ValueError, TypeError):
        if page is not None:
            page.metadata["structured_restore_recovery_error"] = "recovery_write_failed"


def restore_structured_blocks(text, structured_blocks, *, page=None, recovery_dir=None, context=None, channel='body') -> str:
    """Compatibility wrapper; unknown registries never authorize token deletion."""
    result = restore_structured_markdown(text, structured_blocks, context=context)
    record_restore_result(result, structured_blocks, page=page, recovery_dir=recovery_dir, channel=channel)
    return result.text


def _safe_name(value: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+', '_', value).strip('._') or 'document'


def context_for_pages(*pages) -> StructuredRestoreContext:
    """Capture supplied input references before model output can change them."""
    refs = []
    literals = []
    for page in pages:
        refs.extend(page.restore_context.supplied_references)
        literal_counts = Counter(page.restore_context.literal_references)
        literals.extend(page.restore_context.literal_references)
        for match in TABLE_REFERENCE_RE.finditer(page.markdown):
            token = match.group()
            if literal_counts[token]:
                literal_counts[token] -= 1
            else:
                refs.append(token)
    states = [p.restore_context.registry_status for p in pages]
    status = 'complete' if all(s == 'complete' for s in states) else ('incomplete' if 'incomplete' in states else 'unknown')
    return StructuredRestoreContext(tuple(dict.fromkeys(refs)), status, tuple(literals))


def restore_model_outputs(body, cot, blocks, *, page, context, recovery_dir=None):
    body_result = restore_structured_markdown(body, blocks, context=context)
    cot_result = restore_structured_markdown(cot, blocks, context=context) if cot else StructuredRestoreResult(cot)
    record_restore_result(body_result, blocks, page=page, recovery_dir=recovery_dir, channel='body')
    record_restore_result(cot_result, blocks, page=page, recovery_dir=recovery_dir, channel='cot')
    return body_result.text, cot_result.text
