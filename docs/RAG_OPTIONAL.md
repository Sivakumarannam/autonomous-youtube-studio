# Optional RAG (chat knowledge base)

Use only on machines with enough RAM/disk (not the Oracle Always Free 1 GB VM).

## Install

```bash
pip install -r requirements-rag.txt
```

Or in Docker, add a separate stage / profile — do **not** merge into the default
`requirements.txt` used by `docker/docker-compose.oracle.yml`.

## Config

Keep on the 1 GB production VM:

```env
RAG_RESEARCH_ENABLED=false
```

The app starts without FAISS / sentence-transformers (optional imports).
When packages are installed and RAG is enabled, the chatbot can use the vector store.

## Why separate file?

`sentence-transformers` pulls `torch`, which previously pulled multi‑GB CUDA
wheels and filled the free-tier disk. CPU-only pins live here so the main
image stays small.
