# Specifications Repository

Welcome to the `specs/` directory for the **brokenspoke-analyzer** project.

This directory houses the **Specification-Driven Development (SDLD)** artifacts
for our features. Instead of jumping straight into code, we define the "What,"
"How," and "Steps" of a feature in structured markdown documents before
implementation begins. This ensures alignment, reduces rework, and serves as
living documentation for the architecture.

## 🚀 Getting Started

To create a new feature specification:

1.  **Create the directory**: `mkdir specs/XXXX-feature-name/`
2.  **Run the Iterative Prompt**: Use the example bellow (modified for your
    feature) to start a conversation with an LLM. Work with the LLM on each
    document sequentially.
3.  **Refine**: Answer the LLM's questions and iterate until the requirements
    are solid.
4.  **Generate**: Have the LLM output the final `requirements.md`, `design.md`,
    and `tasks.md` one after each other.
5.  **Review**: Have a senior engineer review the generated specs before
    merging.

## 📂 Directory Structure

Each feature gets its own numbered directory to maintain chronological order and
uniqueness:

```text
specs/
└──  xxxx-feature-name/   # Feature #0000: feature-name
    ├── requirements.md  # WHAT the system should do
    ├── design.md        # HOW the system will do it
    └── tasks.md         # STEPS to implement it

```

## 📄 Document Definitions

Every feature directory must contain exactly these three files:

| File                  | Purpose                                                                                                                                                                   | Audience                         |
| :-------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | :------------------------------- |
| **`requirements.md`** | Defines the **functional and non-functional requirements**. Includes user stories, acceptance criteria, and glossary. Focuses on _behavior_ and _constraints_.            | Product Managers, QA, Developers |
| **`design.md`**       | Defines the **technical architecture**. Includes component diagrams, data models, error handling strategies, and integration points. Focuses on _implementation details_. | Developers, Architects           |
| **`tasks.md`**        | Defines the **implementation plan**. A granular checklist of tasks, subtasks, and file paths. Used as the roadmap for the sprint.                                         | Developers, Project Managers     |

## 🔄 The Workflow

We use an **Iterative LLM-Assisted Workflow** to generate these specifications.
This ensures high quality, consistency, and adherence to project constraints.

### Step 1: Initialization (The "Conversation Starter")

We begin by prompting an LLM with the high-level goal and constraints. The LLM
acts as a **Senior Engineer** and asks clarifying questions to fill gaps in our
mental model.

> **Goal**: Identify edge cases, clarify data flows, and confirm technology
> choices before writing a single line of spec.

### Step 2: Iterative Refinement

We answer the LLM's questions, providing specific constraints (e.g., "OSM must
not overwrite," "Use `obstore`," "Directory structure must be X"). The LLM
refines the requirements and design based on this feedback.

### Step 3: Final Generation

Once the conversation reaches a consensus, we use a **Direct Generation Prompt**
to produce the final three markdown files in one go, ensuring all constraints
are baked in.

## 💡 Example: Creating Feature #0000 (Dataset Cache)

Below is an example of the **Step 1** prompt we used to kick off the Dataset
Cache feature. This demonstrates how we guide the LLM to act as a collaborator
rather than just a text generator.

### Example Prompt: Iterative Discovery

```md
Act as a Senior Software Engineer specializing in Specification-Driven LLM
Development (SDLD). Your task is to collaborate with a team to draft a complete
feature specification for a new caching mechanism in an existing Python 3.13
project called "brokenspoke-analyzer".

We will work iteratively. Do not generate the final output immediately. Instead,
guide the conversation, ask clarifying questions, and refine the requirements
based on my inputs.

## Context & Initial State

- **Project**: brokenspoke-analyzer (Python 3.13).
- **Goal**: Implement a file-based caching mechanism for datasets fetched from
  US Census, LODES employment data, and OpenStreetMap (OSM).
- **Constraints**:
  - Must support two modes: Read-Only (for parallel cloud pipelines, up to 1000
    workers) and Read-Write (for sequential local usage).
  - Must auto-detect mode using `os.access`.
  - Must use `platformdirs` for cache location.
  - Must use `obstore` for storage abstraction (future-proofing for cloud).
  - Must use `typer` for CLI and `loguru` for logging.
  - OSM data must be stored in a `latest/` folder and NEVER overwritten
    automatically (manual cleanup only).
  - Must support `--no-cache` flag to bypass caching entirely.
  - Must support `--cache-dir` for custom paths.
  - Must support `cache clean` (with `--source`, `--dry-run`, `--yes` flags).
- **Directory Structure**:
  - Specs: `specs/0000-cache/`
  - Source: `brokenspoke_analyzer/core/cache/`
  - Unit Tests: `tests/brokenspoke_analyzer/core/cache/`
  - Integration Tests: `integration/tests/brokenspoke_analyzer/core/cache/`
  - CLI: `brokenspoke_analyzer/cli/cache.py`
- **Output Templates**: You must eventually produce three markdown files:
  1. `requirements.md` (WHAT)
  2. `design.md` (HOW)
  3. `tasks.md` (STEPS)

## Instructions for the Session

1. **Start**: Begin by acknowledging the role and asking 3-5 high-level
   clarifying questions about the architecture, data flow, or edge cases that
   are not yet defined.
2. **Iterate**: Wait for my answers. Then, propose a draft of `requirements.md`.
   Ask for feedback.
3. **Refine**: Incorporate my feedback (e.g., "OSM should not overwrite," "Test
   directories must mirror source," "Dependencies might already exist").
4. **Design**: Once requirements are locked, draft `design.md` focusing on the
   Registry pattern, Storage Backend, and Data Flow.
5. **Plan**: Finally, draft `tasks.md` with a granular checklist, ensuring all
   directory paths and file names match the constraints exactly.

## Critical Rules

- **Do not hallucinate**: If a detail is missing, ask. Do not invent features.
- **Format**: Output code blocks and markdown tables clearly.
- **Tone**: Professional, analytical, and collaborative.
- **Specifics**: Pay close attention to the directory structure and library
  choices (e.g., `obstore`, `typer`, `loguru`).

Please start the session now by introducing yourself and asking your initial
clarifying questions.
```

### Example Prompt: Implementation

````md
You are a senior software engineer implementing a feature using
Specification-Driven Development (SDLD).

You are given three documents:

- requirements.md (defines WHAT must be built)
- design.md (defines HOW it should be built)
- tasks.md (defines the implementation plan and file structure)

Your task is to execute the tasks and implement the feature.

---

## Rules

- Treat requirements.md as the source of truth for behavior
- Treat design.md as the source of truth for architecture and constraints
- Treat tasks.md as the source of truth for file structure and sequencing

- Do not invent functionality not described in the requirements
- Do not skip or reorder tasks unless strictly necessary for correctness
- Ensure all requirements are fully implemented

- Write production-quality code (no placeholders, no TODOs)
- Include necessary imports and typing
- Keep code modular and testable

---

## Output Format

For each file, output:

```python
# path: <relative/path/to/file.py>

<file content>
```

- Output all files defined in tasks.md
- Do not include explanations
- Do not omit tests

---

## Execution

Read all three documents, then implement the feature.

---

## Optional Guardrails

Additionally:

- Enforce all correctness constraints defined in design.md
- Ensure edge cases are handled (errors, permissions, partial state)
- Ensure tests cover main flows and failure cases
````

### Example Prompt: Review

```md
You are a senior software engineer performing a Specification-Driven Development
(SDLD) code review.

You are given:

- requirements.md (defines WHAT must be built)
- design.md (defines HOW it should be built)
- tasks.md (defines expected structure and scope)
- The full implementation (all generated source and test files)

Your task is to rigorously review the implementation against the specifications.

---

## Review Objectives

1. **Requirements Compliance**
   - Verify every requirement is fully implemented
   - Identify missing, partial, or incorrect behaviors
   - Flag any unintended functionality not defined in requirements.md

2. **Architectural Conformance**
   - Ensure implementation follows design.md
   - Validate correct use of abstractions and patterns
   - Detect architectural violations or shortcuts

3. **Task Completion**
   - Confirm all files defined in tasks.md are present
   - Verify implementation aligns with intended structure
   - Detect missing components or misplaced logic

4. **Correctness & Edge Cases**
   - Validate handling of failure modes and edge cases
   - Check for race conditions, partial writes, and invalid states
   - Ensure correctness properties from design.md are enforced

5. **Code Quality**
   - Evaluate readability, modularity, and maintainability
   - Ensure proper typing, imports, and structure
   - Identify code smells or unnecessary complexity

6. **Test Coverage**
   - Verify tests exist for all major flows
   - Ensure edge cases and failure scenarios are tested
   - Identify missing or weak test cases

---

## Output Format

Produce a structured review report in markdown:

### Summary

- High-level assessment (Pass / Needs Revision / Fail)
- Key risks and concerns

### Findings

For each issue:

- **Severity**: Critical / Major / Minor
- **Category**: Requirements / Design / Tasks / Testing / Quality
- **Location**: File + function/class (if applicable)
- **Issue**: Clear description of the problem
- **Expected**: What the spec requires
- **Recommendation**: Concrete fix

### Coverage Matrix

Map each requirement to implementation status:

- ✅ Implemented
- ⚠️ Partially Implemented
- ❌ Missing

### Test Gaps

- List missing or insufficient test cases

---

## Rules

- Be strict and specification-driven
- Do not assume intent beyond the provided documents
- Do not rewrite the implementation
- Focus on identifying gaps and risks, not style preferences unless impactful

---

## Execution

Review the implementation against all three documents and produce the report.
```

## 📝 Contributing

- **Naming**: Use `YYYY-feature-name` for directories (e.g.,
  `0001-auth-module`).
- **Updates**: If a design changes during implementation, update the `design.md`
  and `tasks.md` to reflect reality. Do not leave specs outdated.
- **Deletion**: Never delete old specs. If a feature is cancelled, mark the
  directory as `cancelled` in the README.
