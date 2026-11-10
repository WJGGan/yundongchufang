"""构建 RAG 嵌入索引：动作库 + 知识卡片 → app/data/index/embeddings.json。

用法：
    uv run python scripts/build_index.py

需要 backend/.env 中配置嵌入密钥（默认复用 ZHIPU_API_KEY）。
动作库或知识卡片内容变更后需重跑本脚本；运行期会按内容 hash 自动识别
过期条目并对其降级词面打分，不会用错旧向量。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.services import rag  # noqa: E402

_BATCH = 16


def _embed_batch(client, texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
        dimensions=settings.embedding_dimensions,
    )
    ordered = sorted(response.data, key=lambda item: item.index)
    return [rag.normalize(item.embedding) for item in ordered]


def main() -> int:
    if not settings.embedding_api_key:
        print("未配置 EMBEDDING_API_KEY / ZHIPU_API_KEY，无法构建索引。", file=sys.stderr)
        return 1

    from openai import OpenAI

    client = OpenAI(
        base_url=settings.embedding_base_url,
        api_key=settings.embedding_api_key,
        timeout=60,
    )

    collections: dict[str, list[dict[str, object]]] = {}
    started = time.time()
    for name, docs in rag.corpus_docs().items():
        items: list[dict[str, object]] = []
        for offset in range(0, len(docs), _BATCH):
            batch = docs[offset : offset + _BATCH]
            vectors = _embed_batch(client, [text for _id, text in batch])
            for (doc_id, text), vector in zip(batch, vectors):
                items.append(
                    {
                        "id": doc_id,
                        "hash": rag.doc_hash(text),
                        "vector": [round(value, 7) for value in vector],
                    }
                )
            print(f"[{name}] 已嵌入 {len(items)}/{len(docs)}")
        collections[name] = items

    rag.INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": settings.embedding_model,
        "dimensions": settings.embedding_dimensions,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "collections": collections,
    }
    with rag.INDEX_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)

    size_kb = rag.INDEX_PATH.stat().st_size / 1024
    total = sum(len(items) for items in collections.values())
    print(
        f"完成：{total} 条向量（{settings.embedding_model}, {settings.embedding_dimensions} 维），"
        f"{size_kb:.0f} KB，耗时 {time.time() - started:.1f}s → {rag.INDEX_PATH}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
