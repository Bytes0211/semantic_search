

# Database Indexing

How semantic search creates indexes from databases

1. Records are extracted from each table sequentially and merged into a single flat list
2. That entire list is passed to one EmbeddingPipeline.run() call
3. Bedrock is called once per batch (10 records at a time), regardless of which table the records came from
4. All vectors land in one NumpyVectorStore

scripts/generate_pg_index.py(148-154)

```bash
    all_inputs: List[EmbeddingInput] = []
    for table in tables:
        all_inputs.extend(extract_inputs(table, TABLE_CONFIGS[table]))
    ...
    store = NumpyVectorStore(dimension=DIM, metric="cosine")
    pipeline = EmbeddingPipeline(provider, store, batch_size=10)
    result = pipeline.run(all_inputs)
```