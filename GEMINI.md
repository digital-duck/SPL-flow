# GEMINI.md: SPL-Flow Project Guide

This document provides essential context for interacting with the SPL-Flow codebase.

## Project Overview

SPL-Flow is a sophisticated AI orchestration platform built in Python. Its primary function is to translate natural language (NL) queries into **Structured Prompt Language (SPL)**, a declarative, SQL-like language for defining complex LLM workflows.

The platform follows a **Mixture-of-Models (MoM)** paradigm. It parses an SPL script, identifies discrete sub-tasks (e.g., code generation, language translation, data analysis), and routes each task to the most suitable specialist LLM in parallel. The results are then composed into a final, coherent response.

A key feature is the **RAG (Retrieval-Augmented Generation) Context Store**, which is built using ChromaDB. Every valid (NL Query, SPL Query) pair from user sessions is automatically captured. This creates a "digital twin flywheel," where the system learns from real-world usage to improve the accuracy of future NL-to-SPL translations by providing dynamic few-shot examples.

The project is architected to be **API-first**, with a core programmatic interface defined in `src/api.py`. The command-line interface (CLI) and Streamlit-based web UI are thin wrappers around this central API.

## Core Technologies

-   **Backend**: Python
-   **Orchestration**: `pocketflow` (defines the execution graph) and `spl-llm` (the SPL engine)
-   **CLI**: `click`
-   **Web UI**: `streamlit`
-   **Vector Store**: `chromadb`
-   **Dependencies**: Managed via `pyproject.toml` and `requirements.txt`.

## Building and Running

### 1. Installation

First, install the required Python dependencies. For local development, the repository is set up to use editable installs for sibling projects (`SPL`, `dd-logging`).

```bash
# Install all dependencies from requirements.txt
pip install -r requirements.txt
```

### 2. Running the Web UI

The user interface is a multi-page Streamlit application. A helper script is provided to launch it.

```bash
# Launch the Streamlit UI
bash 000_run_ui.sh
```

Alternatively, you can run streamlit directly:
```bash
streamlit run src/ui/streamlit/🌊SPL_Flow_App.py
```

### 3. Using the CLI

The project includes a powerful CLI for scripting and batch processing. The main entry point is `src.cli`.

**Common Commands:**

-   **`generate`**: Translates a natural language query into SPL without executing it.
    ```bash
    python -m src.cli generate "List 10 Chinese characters with the water radical."
    ```

-   **`run`**: Executes the full pipeline: NL -> SPL -> Execute -> Result.
    ```bash
    python -m src.cli run "Summarize this article" --context-file article.txt
    ```

-   **`exec`**: Executes a pre-written `.spl` file directly.
    ```bash
    python -m src.cli exec my_query.spl --params "topic=AI"
    ```

-   **`benchmark`**: Runs a single `.spl` file against multiple models in parallel to compare outputs, performance, and cost.
    ```bash
    python -m src.cli benchmark compare.spl --models "auto,openai/gpt-4o" --adapter openrouter
    ```

## Development Conventions

### Architecture

-   **API-First**: All core logic is exposed via `src/api.py`. The CLI and UI are clients of this API. This is the primary interface for any new integrations.
-   **Flow-Based Orchestration**: The sequence of operations (e.g., `generate` -> `validate` -> `execute`) is defined as a graph using the `pocketflow` library in `src/flows/spl_flow.py`.
-   **Node-Based Logic**: Individual processing steps are encapsulated in `Node` classes within the `src/nodes/` directory (e.g., `Text2SPLNode`, `ExecuteSPLNode`).
-   **RAG Store**: The vector store logic is abstracted in `src/rag/`, with a factory to retrieve the configured store (defaulting to ChromaDB).

### Code Style

-   The code is typed and well-documented with docstrings.
-   Logging is configured via `src/utils/logging_config.py` and is used extensively throughout the application.
-   Configuration is minimal, with `splflow.yaml` primarily used to set the default LLM adapter.

### Testing

-   The `README.md` mentions a `README-TEST.md` file for step-by-step testing guidance.
-   The `tests/` directory exists but appears to be in the early stages of development. When adding new features, corresponding tests should be added.

## Key Files

-   `README.md`: The canonical source of truth for the project's vision, features, and usage.
-   `src/api.py`: The **primary public interface**. All system-to-system integrations should use this.
-   `src/cli.py`: The `click`-based command-line interface.
-   `src/flows/spl_flow.py`: Defines the `pocketflow` graphs that orchestrate the different nodes.
-   `src/nodes/`: Contains the core logic for each step in the pipeline.
-   `src/ui/streamlit/`: The root for the multi-page Streamlit application.
-   `src/rag/`: Contains the implementation for the RAG vector store.
-   `src/utils/model_router.py`: Implements the Mixture-of-Models (MoM) routing logic.
-   `splflow.yaml`: A simple YAML file for top-level application configuration.
-   `requirements.txt` / `pyproject.toml`: Project dependency definitions.
