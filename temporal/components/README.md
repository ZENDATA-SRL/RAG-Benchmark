# components

Executable implementations of the builtin components. The matching declarations (key,
version, `params_schema`) live in `backend/src/components/builtin/`; this package must never
be imported by the backend (dependencies flow `temporal → backend`).

| Package | Contents |
|---|---|
| `parsers/` | `pypdf.py` (`PyPdfParser`), `plumber.py` (`PdfPlumberParser`), `normalization.py` (ligatures, smart quotes, NFKC so lexical matching is stable), `exceptions.py` (`PermanentParsingError`: corrupt, encrypted or text-less files, never retried) |
| `chunkers/` | `recursive.py` (`RecursiveChunker`), `markdown.py` (`MarkdownChunker`), `header_footer.py` (`strip_headers_footers`, document-local page-furniture removal, on by default), `page_mapping.py` (`PagedText`: character offsets back to pages, so each chunk records its page span) |
| `embedders/` | `shared.py`: `BUILTIN_EMBEDDERS` (key → factory taking the profile params) and `resolve_embedder(key, params)`, returning LangChain `Embeddings` for `openai` and `bedrock` |
| `vector_stores/` | `chroma.py`: `ChromaVectorStore` (`ensure_collection(name, index_params)` with the profile's HNSW keys, `upsert(name, ids, embeddings, documents, metadatas)`) and `build_chroma_store()`, an HTTP client on `CHROMA_HOST`/`CHROMA_PORT`; `qdrant.py`: `QdrantVectorStore` (the collection is created at the first `upsert`, because the vector size is only known then) and `build_qdrant_store()`, a client on `QDRANT_HOST`/`QDRANT_PORT` |

`__init__.py` holds `BUILTIN_PARSERS`, `BUILTIN_CHUNKERS`, `BUILTIN_VECTOR_STORES`,
`resolve_parser`, `resolve_chunker`, `resolve_vector_store` and `assert_registry_complete()`,
run at worker start over all four component types.

## Contracts

- A parser has `parse(stream, filename) -> ParseOutput` (`{pages: [{page, text}], metadata}`).
- A chunker has `chunk(parse_output, params) -> list[ChunkPayload]`; each payload has
  `text`, `modality`, `metadata` (including the page span) and `text_normalized`.
- Both are stateless and document-scoped: they see one document, never the corpus.
- An embedder is built per profile (factory), since it is bound to the profile's model and
  credentials.
- A vector store writes one collection per index build. The upsert is keyed by chunk id,
  so re-running a batch overwrites it instead of duplicating vectors.

## Adding a component

See "Adding a builtin component" in `backend/src/components/README.md`.
