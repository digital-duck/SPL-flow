# Objective Review: CLAUDE.md vs. GEMINI.md

This document provides a comparative analysis of two instructional context files, `CLAUDE.md` and `GEMINI.md`, both designed to guide an AI assistant in understanding and working with the SPL-Flow project.

---

## 1. Commonalities

Both files serve the same fundamental purpose: to provide a condensed guide for an AI to quickly understand the SPL-Flow project. They share several key sections:

-   **Project Purpose**: Both explain that SPL-Flow is a Mixture-of-Models (MoM) orchestration platform that translates natural language into SPL.
-   **Core Commands**: Both list the essential shell commands for installing dependencies (`pip install`), running the UI (`streamlit run`), and using the CLI (`python -m src.cli`).
-   **Architecture Overview**: Both touch on the project's architecture, mentioning the PocketFlow graph, the different nodes, and the use of LLM adapters.
-   **Technology Stack**: Both implicitly or explicitly identify the key technologies involved (Python, Streamlit, PocketFlow, SPL).

---

## 2. Pros and Cons

### GEMINI.md

-   **Pros**:
    -   **Superior Onboarding Structure**: It is written like a well-structured onboarding document. It starts with a high-level "Project Overview," then logically drills down into technologies, usage patterns, development conventions, and key files. This top-down approach is excellent for building foundational context.
    -   **Conceptual Clarity**: It does a better job of explaining the *why* behind the project, particularly the "RAG Context Store" and the "digital twin flywheel" concept.
    -   **Verified Commands**: The command to run the Streamlit UI (`streamlit run src/ui/streamlit/🌊SPL_Flow_App.py`) is correct, which was discovered through investigation. The `CLAUDE.md` file contains an outdated, non-functional command.
    -   **API-First Emphasis**: It correctly identifies and emphasizes that the project is "API-first" and that `src/api.py` is the primary public interface, which is a crucial architectural insight.

-   **Cons**:
    -   **Lacks Implementation "Gotchas"**: It is missing critical, low-level implementation details that are vital for debugging and modification. For example, it does not mention the hardcoded `sys.path` modifications or the exact structure of the `shared` dictionary that passes state between nodes.
    -   **Less Detailed Node Descriptions**: While it mentions the nodes, it doesn't detail the specific responsibility of each one, which `CLAUDE.md` does.

### CLAUDE.md

-   **Pros**:
    -   **Rich in Technical Detail**: Its strength lies in its depth. It provides a detailed breakdown of each node's responsibility, the structure of the `shared` store dictionary, and information about the few-shot prompt construction in `spl_templates.py`.
    -   **Highlights Critical Constraints**: The "Important Constraints" section is extremely valuable. It explicitly states that the test suite is empty, async email is a stub, and explains which LLM is used for the Text2SPL step. This is crucial information for an AI to avoid making incorrect assumptions.
    -   **Exposes "Hacks"**: It correctly identifies the `sys.path.insert` hack, which is a non-obvious dependency crucial for running the application.

-   **Cons**:
    -   **Weaker Structure**: It reads more like a technical reference or a brain-dump of important facts rather than a structured guide. It lacks the narrative flow of `GEMINI.md`, making it less suitable for a first-time introduction.
    -   **Contains Errors**: The command for running the Streamlit UI is incorrect, pointing to a file (`app.py`) that does not exist in the final version of the code.
    -   **Less Introductory**: The initial project summary is brief and dives into technical specifics very quickly.

---

## 3. The Ideal Guide

An ideal guide would synthesize the strengths of both documents, creating a guide that is both a comprehensive introduction and a detailed technical reference. It would be structured as follows:

1.  **Project Overview (from `GEMINI.md`)**: Start with the high-level, conceptual overview to establish the "what" and "why". This provides a strong foundation.

2.  **Building and Running (from `GEMINI.md`)**: Use the verified and clearly explained commands for installation, UI, and CLI usage.

3.  **Architecture Deep Dive (A Hybrid Approach)**:
    *   Begin with the high-level architectural summary from `GEMINI.md`.
    *   Incorporate the detailed PocketFlow graph diagram and the "Shared Store" dictionary structure from `CLAUDE.md` to explain the internal data flow mechanics.
    *   Add the detailed "Node Responsibilities" breakdown from `CLAUDE.md`.
    *   Include the critical note about the `sys.path` dependency from `CLAUDE.md`.

4.  **Important Constraints & Project State (from `CLAUDE.md`)**: Dedicate a section to the "Important Constraints" from `CLAUDE.md`. This is arguably the most valuable section for a working AI agent, as it clearly defines the project's current limitations and prevents wasted effort.

5.  **Development Conventions & Key Files (from `GEMINI.md`)**: Conclude with the list of key files and general development conventions to guide future code modifications.

By combining the top-down, narrative structure of `GEMINI.md` with the bottom-up, detail-rich content of `CLAUDE.md`, the resulting guide would provide an AI assistant with a complete and actionable understanding of the project, from high-level purpose to low-level implementation details and constraints.

### Custom Prompt to Generate the Ideal Guide

If you want to instruct an LLM to generate a guide that combines these strengths, you could use a prompt like the one below. This prompt is specifically engineered to ask for both a high-level overview and critical low-level details.

```prompt
You are an expert AI software engineer tasked with creating a comprehensive `GUIDE.md` for a new project. This guide will be the primary source of truth for other AI developers and human engineers to quickly get up to speed.

Your task is to analyze the provided project directory and produce a well-structured markdown file that is both an easy-to-read onboarding document and a detailed technical reference.

**Analysis Process:**

1.  **Initial Exploration:** Get a high-level overview by listing files and reading the main `README.md`.
2.  **Deep Dive:** Select and read up to 10 key files to understand the project's core logic, dependencies, and structure. Pay close attention to configuration files, API entry points, core logic/flow definitions, and build scripts.
3.  **Synthesize Findings:** Based on your analysis, generate the `GUIDE.md` with the following structure.

**`GUIDE.md` Structure and Content:**

Your generated guide **MUST** contain the following sections in this order:

1.  **Project Overview**: A clear, high-level summary. Explain the project's purpose, what problem it solves, and its core concepts.
2.  **Building and Running**: Provide **verified** commands for installation, building, running the main application(s) (e.g., UI, server), and running tests. If you discover helper scripts, prefer them.
3.  **Architecture Deep Dive**: This is the most critical section.
    *   Provide a high-level architectural summary.
    *   Detail the core components/nodes and their specific responsibilities.
    *   Explain the data flow between components. If there's a central data object or "store" passed between them, describe its structure.
    *   **Crucially, identify and document any non-obvious implementation details or "hacks,"** such as hardcoded paths, `sys.path` modifications, or unusual dependencies.
4.  **Important Constraints, Assumptions, and Gotchas**: Explicitly create a list of the project's current limitations.
    *   Are there empty directories (e.g., `tests/`) that imply future work?
    *   Are some features mentioned in the documentation but implemented as stubs?
    *   Are there specific version constraints or known issues with certain environments?
5.  **Development Conventions**: Describe any coding styles, testing practices, or contribution guidelines you can infer from the codebase.
6.  **Key Files**: List the most important files and briefly explain what they contain.

Your final output should be only the complete markdown content for the `GUIDE.md` file.
```
