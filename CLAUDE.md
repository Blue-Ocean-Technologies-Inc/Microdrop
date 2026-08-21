# Claude guidance for this repository

## Coding style (project-wide)

- **Format all Python with `black`** (default settings) before committing.
  Run it on every file you create or modify:
  `black <changed files>`.
- **Separate logical chunks of code with blank lines** inside functions —
  setup, action, and result-handling blocks should read as visually
  distinct paragraphs, not one dense run of statements. Prefer a short
  comment above a chunk when its purpose isn't obvious.
- Keep functions short and single-purpose; if a function needs section
  comments to stay navigable, consider splitting it.
- These rules exist so reviewers can follow the code easily — optimize
  for readability over compactness.
