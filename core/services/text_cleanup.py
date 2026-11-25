from __future__ import annotations

import re


def truncate_repeats(text, max_len=3):
    text = re.sub(r"(\D)\1{" + str(max_len) + r",}", lambda m: m.group(1) * max_len, text)
    text = re.sub(r"(\n){" + str(max_len + 1) + r",}", "\n" * max_len, text)
    return text


def merge_ocr_branch_results(base_res, text_res, table_res, image_res):
    """Merge legacy branch results by page and stable block identity.

    Positional merging silently paired unrelated blocks when a branch filtered or
    reordered its layout detections. Legacy callers should provide ``block_id``;
    ``reading_order`` is accepted as the compatibility fallback.
    """
    branches = {
        "text": _index_branch(text_res),
        "table": _index_branch(table_res),
        "image": _index_branch(image_res),
    }
    for page in base_res:
        base_items = page.get("layout_dets", [])
        page_key = _page_key(page)
        if page_key is None:
            continue

        for base_item in base_items:
            block_key = _block_key(base_item)
            if block_key is None:
                continue
            text_item = branches["text"].get((page_key, block_key))
            table_item = branches["table"].get((page_key, block_key))
            image_item = branches["image"].get((page_key, block_key))
            if text_item:
                if "text" in text_item:
                    base_item["text"] = text_item["text"]
                if "score" in text_item:
                    base_item["score"] = text_item["score"]

            if table_item:
                if "text" in table_item and table_item["text"]:
                    base_item["text"] = table_item["text"]
                if "table_html_raw" in table_item:
                    base_item["table_html_raw"] = table_item["table_html_raw"]

            if image_item and "text" in image_item and image_item["text"]:
                base_item["text"] = image_item["text"]

    return base_res


def _index_branch(pages):
    indexed = {}
    for page in pages or []:
        page_key = _page_key(page)
        if page_key is None:
            continue
        for item in page.get("layout_dets", []):
            block_key = _block_key(item)
            if block_key is not None:
                indexed[(page_key, block_key)] = item
    return indexed


def _page_key(page):
    page_info = page.get("page_info", {})
    return page_info.get("page_no") if isinstance(page_info, dict) else None


def _block_key(item):
    block_id = item.get("block_id")
    if block_id is not None:
        return ("block_id", str(block_id))
    reading_order = item.get("reading_order")
    if reading_order is not None:
        return ("reading_order", str(reading_order))
    return None
