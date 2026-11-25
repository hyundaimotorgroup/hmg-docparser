"""Beta page-scoped wrapper for role-specific block restoration."""
from __future__ import annotations

from core.domain.layout.models import PageEnrichedDTO
from core.engine.config.node_config import BlockContextRestoreConfig
from core.interfaces.node import Node, NodeContext, NodeResult
from core.observability.llm_usage import build_llm_observability
from core.observability.router_reports import append_router_records
from core.services.block_context_restore import restore_page_block_context
from core.services.model_routing import node_model_options


class BlockContextRestoreNode(Node):
    node_name = 'layout.block_context_restorer'
    input_type = 'page_enriched_dto@v1'
    output_type = 'page_enriched_dto@v1'

    def run(self, context: NodeContext, value: object) -> NodeResult:
        single = isinstance(value, PageEnrichedDTO)
        pages = [value] if single else value
        if not isinstance(pages, list) or not all(isinstance(p, PageEnrichedDTO) for p in pages):
            raise TypeError('block_context_restorer expects PageEnrichedDTO or list[PageEnrichedDTO]')
        options = BlockContextRestoreConfig.model_validate(dict(context.config)).model_dump(exclude_none=True)
        options.pop('progress_weight', None)
        options.update(node_model_options(context))
        runtime = context.metadata.get('runtime_config', {})
        deadline = runtime.get('mlapi_deadline_monotonic') if isinstance(runtime, dict) else None
        callback, metadata = build_llm_observability(context)
        output = [restore_page_block_context(
            page, **options, source_node_id=context.node_id,
            usage_callback=callback, trace_metadata=metadata,
            cancellation_check=context.metadata.get('cancellation_check'),
            deadline_monotonic=deadline,
        ) for page in pages]
        evidence = []
        for page in output:
            contexts = [b.metadata['block_context_restore'] for b in page.blocks
                        if isinstance(b.metadata.get('block_context_restore'), dict)
                        and b.metadata['block_context_restore'].get('role') == options['block_kind']]
            evidence.append({'page_no': page.page.page_no, 'document_id': page.page.document_id,
                             'node_id': context.node_id, 'block_kind': options['block_kind'],
                             'restored_count': sum(c.get('status') == 'restored' for c in contexts),
                             'failed_count': sum(c.get('status') == 'failed' for c in contexts),
                             'actual_attempts': sum(c.get('attempts', 0) for c in contexts),
                             'blocks': [{k: c[k] for k in ('block_id', 'status', 'attempts', 'error_code') if k in c} for c in contexts]})
        append_router_records(context, 'block_context_report.jsonl', evidence)
        return NodeResult(value=output[0] if single else output, metadata={
            'page_count': len(output), 'block_kind': options['block_kind'],
            **{key: sum(e[key] for e in evidence) for key in ('restored_count', 'failed_count', 'actual_attempts')},
        })
