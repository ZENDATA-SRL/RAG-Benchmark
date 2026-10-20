# components

Executable implementations of the builtin components. The matching declarations (key,
version, `params_schema`) live in `backend/src/components/builtin/`; this package must never
be imported by the backend (dependencies flow `temporal → backend`).

| Package | Contents |
|---|---|
| `parsers/` | `pypdf.py` (`PyPdfParser`), `plumber.py` (`PdfPlumberParser`), `normalization.py` (ligatures, smart quotes, NFKC so lexical matching is stable), `exceptions.py` (`PermanentParsingError`: corrupt, encrypted or text-less files, never retried) |
| `chunkers/` | `recursive.py` (`RecursiveChunker`), `markdown.py` (`MarkdownChunker`), `header_footer.py` (`strip_headers_footers`, document-local page-furniture removal, on by default), `page_mapping.py` (`PagedText`: character offsets back to pages, so each chunk records its page span) |
| `embedders/` | `shared.py::resolve_embedder(key, params)`: LangChain `Embeddings` for `openai` and `bedrock` |

`__init__.py` holds `BUILTIN_PARSERS`, `BUILTIN_CHUNKERS`, `resolve_parser`,
`resolve_chunker` and `assert_registry_complete()` (run at worker start; covers parsers and
chunkers only, not embedders).

## Contracts

- A parser has `parse(stream, filename) -> ParseOutput` (`{pages: [{page, text}], metadata}`).
- A chunker has `chunk(parse_output, params) -> list[ChunkPayload]`; each payload has
  `text`, `modality`, `metadata` (including the page span) and `text_normalized`.
- Both are stateless and document-scoped: they see one document, never the corpus.

## Adding a component

See "Adding a builtin component" in `backend/src/components/README.md`.
