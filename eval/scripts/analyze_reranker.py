import json

with open("eval/results/reranker_eval.json", encoding="utf-8") as f:
    data = json.load(f)

print("=== Negative queries with rerank scores ===")
for q in data["queries"]:
    if not q["expected_sources"]:
        top = q["hits"][0] if q["hits"] else {}
        print(
            f'  {q["id"]}: rerank={top.get("rerank_score", 0):.4f} '
            f'cos={top.get("cosine_score", 0):.4f} '
            f'bm25={top.get("bm25_score", 0):.4f} '
            f'src={top.get("source", "?")[:40]} | {q["query"][:50]}'
        )

print()
print("=== All queries: top-1 rerank scores ===")
for q in data["queries"]:
    if q["hits"]:
        top = q["hits"][0]
        marker = "~" if not q["expected_sources"] else ("+" if q["matched"] else "x")
        print(
            f'  [{marker}] {q["id"]}: rerank={top["rerank_score"]:.4f} '
            f'cos={top["cosine_score"]:.4f} '
            f'src={top["source"][:35]}'
        )
