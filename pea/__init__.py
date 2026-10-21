"""
Power Electronics AI Agent (PEA) — Python package layout:

- ``pea.tools`` — Design math and ``execute_tool`` dispatch (``calculator.py``);
  LangChain ``@tool`` wrappers in ``langchain_tools.py`` for the LLM.
- ``pea.agent`` — ``PEAAgent``: OpenAI chat + tool calls + optional RAG context.
- ``pea.knowledge`` — Curated snippets in ``documents.py``; ``KnowledgeRetriever``
  (ChromaDB + embeddings, or keyword fallback).
- ``pea.thermal`` — Pure-Python thermal design: shared-sink networks and
  Foster/Cauer impedances (``network.py``), loss(Tj) iteration
  (``electrothermal.py``), natural/forced/liquid cooling comparison
  (``cooling.py``), Stage A heat-sink Pareto screening
  (``heatsink_optimisation.py``) using the sibling HeatSinkOptimisation
  checkout, the DAB case study (``dab_case.py``) and ``python -m pea.thermal``.
- ``pea.cli`` — ``pea`` console entry point.
- ``pea.desktop`` — ``pea-desktop`` / ``python -m pea.desktop``: pywebview shell
  for the static ``index.html`` UI at the repo root.

Repo root also has ``app.py`` (Streamlit: same calculators + agent) and
``index.html`` (standalone browser UI; no Python required for layout/calculator stubs).
"""

__version__ = "0.1.0"
