import subprocess
from pathlib import Path
from llama_index.core import Document
from llama_index.core.node_parser import MarkdownNodeParser

pdf = Path("data/rag_ustav/Korabelny_ustav_VMF_2022.pdf")
out = Path("data/parsed")

subprocess.run(
    ["chandra", str(pdf), str(out), "--method", "vllm"],
    check=True,
)

markdown = next(out.rglob(f"{pdf.stem}.md"))
document = Document(
    text=markdown.read_text(encoding="utf-8"),
    metadata={"source": pdf.name, "parser": "chandra-ocr-2"},
)

nodes = MarkdownNodeParser().get_nodes_from_documents([document])