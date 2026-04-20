# Prisma-research-flow-V1
Prisma research flow V1 — A Claude Code-native multi-agent research engine. Turns research questions into professional think-tank reports (thesis-driven, adversarial, with tables &amp; scenarios). Features strict process hooks, mixed-model planning, and robust citation handling. Built for high-quality, balanced, production-ready analysis.

## What it is

Most AI research tools are wrappers: they call a single model, stream results, and call it done. This system is different. It implements the [Anthropic multi-agent research architecture](https://www.anthropic.com/engineering/multi-agent-research-system) — with a Lead Orchestrator that plans, parallel Subagents that search independently in their own context windows, a Red Team auditor that checks for missing adversarial perspectives, and a dedicated citation pass — all running inside Claude Code with full visibility into every agent's actions.

The result is a **5,000–10,000 word structured report** with:
- A disputable thesis statement (not a neutral summary)
- Evidence from multiple independent sources with adversarial balance
- ≥3 analytical tables including a scenario probability matrix
- APA-format citations with retrieval dates
- A scenario forecast section with probability-weighted paths

---

## Architecture

<img width="1267" height="832" alt="40d52cdcb628a962a42b48dbe2efb43a" src="https://github.com/user-attachments/assets/6a0dcff4-2593-4c3e-b4bf-6ffdb1a254a6" />


```
/deep-research <topic>
       │
       ▼
[Hook] preflight_check ──→ env / deps / API key validation
       │
       ▼
Lead Researcher  (orchestrator · Claude Sonnet)
  │
  ├── Phase 0:  Intent clarification  (if ambiguous)
  │
  ├── Phase 0.5: Generate task slug   taiwan_0418
  │             Create  findings/taiwan_0418/
  │                      output/taiwan_0418/
  │             Write   output/.current_slug
  │
  ├── Phase 1:  Research Plan  ── three-step gate ──────────────────┐
  │             │                                                    │
  │             ├─ Bash: llm_plan.py  (Gemini 2.5 / any OpenAI-compat model)
  │             ├─ Show full plan + [1]/[2]/[3] choice in conversation
  │             ├─ [Hook] pre_write_check blocks write until confirmed
  │             └─ User confirms → touch .plan_confirmed → write plan.md
  │
  ├── Phase 2:  Parallel web-researcher spawn  (max 5 + up to 3 delayed)
  │             │
  │             ├─ Batch 1: up to 5 Tasks launched in one turn ──────────┐
  │             │   web-researcher · Claude Sonnet · independent context  │
  │             │   WebSearch + WebFetch + Tavily (8-key failover)        │ parallel
  │             │   writes  findings/taiwan_0418/sub_a.json               │
  │             └─ Batch 2: remaining Tasks after Batch 1 completes ──────┘
  │
  ├── Phase 3:  gap-analyzer  (Sonnet)
  │             ├─ Coverage check  (data count, source diversity, recency)
  │             └─ Red team check  (adversarial perspective per dimension)
  │             → [VERDICT: COMPLETE | NEEDS_MORE]
  │             → If NEEDS_MORE: spawn supplemental researchers (1 round max)
  │
  ├── Phase 4:  synthesizer  (Opus · extended thinking)
  │             ├─ 9-point pre-writing review in extended thinking
  │             ├─ Gemini Deep Research prose style
  │             ├─ Vocabulary frequency caps (no overused buzzwords)
  │             ├─ Data precision rules (no vague "overwhelming majority")
  │             └─ [Hook] post_write_check scans output automatically
  │
  ├── Phase 5a: citation-agent  (Haiku/Sonnet · ≤15 min)
  │             └─ Lightweight mapper only: {"[reuters.com]": "(Reuters, 2024)"}
  │                writes  output/taiwan_0418/citations_map.json
  │
  ├── Phase 5b: apply_citations.py  (pure Python · never times out)
  │             ├─ Batch .replace() all placeholders
  │             ├─ Appends full References section with Retrieved dates
  │             └─ Fallback: keeps placeholders + appends "APA pending" appendix
  │
  └── [Hook] final_quality_gate
              ├─ 60-second async wait for background agents to finish
              ├─ Hard block only on zero-output (1 block max)
              └─ Soft warning otherwise — never dead-loops
```
<img width="1403" height="1279" alt="d33ad757472934fb80fdf7e5dbb02821" src="https://github.com/user-attachments/assets/8a962657-79c6-4e50-a093-853d63d577fa" />

---

## Key design decisions

### Native Claude Code agents, not API wrappers

Each subagent is defined as a `.claude/agents/*.md` file with its own model assignment, tool list, and behavioral prompt. Claude Code launches them as true parallel tasks with **independent context windows** — the "separation of concerns" property that Anthropic's internal research found produces 90.2% better results than single-agent approaches.

### Hooks as a process contract

Five hooks enforce discipline that LLM-only prompts cannot guarantee reliably:

| Hook | Trigger | What it enforces |
|------|---------|-----------------|
| `preflight_check` | On `/deep-research` submit | Validates all API keys, deps, and Tavily key count before wasting budget |
| `pre_write_check` | Before any `Write` to `plan.md` | **Hard-blocks** writing until user has seen the plan and confirmed in chat |
| `post_write_check` | After any `Write` | Validates JSON structure, checks vocabulary caps, flags banned phrases |
| `post_task_log` | After any `Task` | Logs subagent activity to slug-specific `workflow.log` |
| `final_quality_gate` | On `Stop` | 60s async wait, then soft-warns or single hard-block on zero output |

The `pre_write_check` hook solves a specific hallucination pattern observed in testing: the orchestrator would `Write` the plan file, *then* present the [1]/[2]/[3] confirmation options — bypassing user review. The hook makes this structurally impossible.

### Task-scoped file isolation (slug system)

Every run generates a slug (e.g., `taiwan_0418`) from the task name + date. All artifacts go into `findings/<slug>/` and `output/<slug>/`. This prevents cross-contamination between runs and makes it trivial to compare or resume past research sessions.

### Two-stage citation pipeline

The citation agent was consistently timing out when asked to read and rewrite 30,000+ character reports. The v3 architecture splits the work:

1. `citation-agent` (Haiku) reads only the small findings JSONs and outputs a compact `citations_map.json` dictionary — a task it can complete in under 15 minutes
2. `apply_citations.py` (pure Python) does the actual text replacement — instantaneous, deterministic, never times out

If the agent times out anyway, `apply_citations.py` runs in fallback mode: placeholders are preserved, an "APA pending" appendix is added, and `report_final.md` is always produced.

### Mixed-model cost optimization

| Role | Model | Why |
|------|-------|-----|
| Orchestrator | Claude Sonnet (Code built-in) | Coordination logic |
| Planner | Gemini 2.5 Flash / Pro | Long context, permissive content policy, cheaper than Opus for structured planning |
| Query generator | DeepSeek-V3.2 | Strong at Chinese query generation, very cheap for a repetitive subtask |
| Web researcher (×N) | Claude Sonnet | Needs reasoning, parallel context isolation |
| Gap analyzer | Claude Sonnet | Structured judgment, pattern matching |
| Synthesizer | Claude Opus | Highest quality prose generation, extended thinking |
| Citation agent | Claude Haiku/Sonnet | Simple mapping task, fast, cheap |

Estimated cost per full research run: **$3–8 USD** depending on topic complexity.

---

## Requirements

- [Claude Code](https://claude.ai/code) v2.1+
- Python 3.10+
- API access or direct Anthropic API
- A planning-layer LLM with OpenAI-compatible API (Gemini, DeepSeek, Grok, GPT — any)
- At least 1 [Tavily](https://tavily.com) API key (up to 8 for parallel failover)

---

## Installation

```bash
git clone https://github.com/20240610ldx-hub/Prisma-research-flow-V1
cd Prisma-research-flow-V1
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and fill in your keys. Minimum viable configuration:

```env
PLANNER_API_KEY=sk-...          # Any OpenAI-compatible API key
PLANNER_BASE_URL=
PLANNER_MODEL=gemini-2.5-flash  # Or: deepseek-v3.2-exp, gpt-4o, grok-4

ANTHROPIC_API_KEY=sk-...        # Claude API key (direct or via proxy)
ANTHROPIC_BASE_URL=  # Remove if using Anthropic directly

TAVILY_API_KEY_1=tvly-...       # At least one required
```

Then open this directory in Claude Code:

```bash
claude
```

---

## Usage

```
/deep-research <your research topic>
```

**Examples:**

```
/deep-research The strategic implications of DeepSeek's open-weight release for US AI export controls

/deep-research Structural vulnerabilities in China's local government debt and transmission to the banking system

/deep-research How Taiwan's 2024 election results reshape cross-strait deterrence calculus through 2030
```

### What you will see

```
[Hook] preflight_check  ✓ env ready · 6 Tavily keys detected

Phase 0: Topic is sufficiently specific — skipping clarification

Phase 0.5:
● Bash(python scripts/init_slug.py "The strategic implications of ...")
  └─ slug: deepseek_0418
     Created: findings/deepseek_0418/  findings/deepseek_0418/.tmp/
              output/deepseek_0418/
     Wrote: output/.current_slug

Phase 1:
● Bash(python scripts/llm_plan.py --task "..." --output output/taiwan_0418/plan.md)
  └─ [stdout: full modular research plan]

  Here is the generated research plan:
  ─────────────────────────────────────
  I. Research Subject Definition ...
  II. Status Assessment ...
  III. Four Analytical Dimensions ...
  ...
  ─────────────────────────────────────
  Please choose:
    [1] Confirm — start deep research
    [2] Modify a dimension
    [3] Add a new requirement

> 1

● Bash(touch output/taiwan_0418/.plan_confirmed)
● Write(output/taiwan_0418/plan.md)   [Hook: pre_write_check ✓ confirmed]

Phase 2: Spawning 6 researchers (Batch 1: 5, Batch 2: 1)

● Task(web-researcher) sub_a · Dimension A: PLA modernization
● Task(web-researcher) sub_b · Dimension B: Taiwan domestic politics   ← launched
● Task(web-researcher) sub_c · Dimension C: US strategic posture          in one
● Task(web-researcher) sub_d · Dimension D: Economic interdependence       turn
● Task(web-researcher) sub_e · Dimension D split: semiconductor supply ─── (parallel)
  ├─ sub_a: 5 searches · 7 fetches · 9 findings ✓
  ├─ sub_b: 4 searches · 8 fetches · 8 findings ✓
  ├─ sub_c: 5 searches · 6 fetches · 7 findings ✓
  ├─ sub_d: 4 searches · 7 fetches · 8 findings ✓
  └─ sub_e: 5 searches · 8 fetches · 9 findings ✓

● Task(web-researcher) sub_f · Adversarial perspectives (Batch 2)
  └─ sub_f: 3 searches · 5 fetches · 6 findings ✓

Phase 3:
● Task(gap-analyzer) coverage audit + red team check
  └─ Dimension C: adversarial perspective thin — adding supplemental query
  └─ [VERDICT: NEEDS_MORE]
● Task(web-researcher) supp_1 · adversarial: US credibility skeptics
  └─ supp_1: 3 searches · 4 fetches · 5 findings ✓

Phase 4:
● Task(synthesizer) ← Opus · extended thinking
  └─ output/taiwan_0418/report_draft.md (8,847 chars · 5 tables)
  └─ [Hook post_write_check: ✓ no banned phrases · vocabulary caps OK]

Phase 5a:
● Task(citation-agent) ← Haiku · mapping only
  └─ output/taiwan_0418/citations_map.json (34 entries)

Phase 5b:
● Bash(python scripts/apply_citations.py --slug taiwan_0418)
  └─ 34 placeholders replaced · References appended
  └─ output/taiwan_0418/report_final.md ✓

[Hook] final_quality_gate ✓ all checks passed

Deep research complete
─────────────────────────────────────────────
Task slug:     taiwan_0418
Report:        output/taiwan_0418/report_final.md
Length:        ~8,400 characters
Tables:        5 (including scenario probability matrix)
References:    34 (APA format · Retrieved 2026-04)
Core thesis:   Beijing's coercive toolkit is exhibiting diminishing returns,
               while Taiwan's internal political fractures and Washington's
               credibility erosion are simultaneously narrowing the space for
               status quo maintenance — making the next five to ten years the
               most structurally fragile window this equilibrium has faced.
Buzzword audit: structural × 3 / paradox × 2 / deadlock × 1  (all within caps)
─────────────────────────────────────────────

<img width="1729" height="21335" alt="5ec19e17bab8791c57f86272c15ea577" src="https://github.com/user-attachments/assets/27564e85-59ee-4c70-8ac7-982fc0aacb08" />
<img width="861" height="463" alt="c65296340e12b40b71d5397687ffcfac" src="https://github.com/user-attachments/assets/a5c8e6e4-015f-4447-a32a-a321b548356e" />

```

---

## Configuration reference

### Planning layer (`PLANNER_*`)

The planner generates the modular research plan. Any OpenAI-compatible API works.

| Variable | Default | Description |
|----------|---------|-------------|
| `PLANNER_API_KEY` | — | Primary key |
| `PLANNER_API_KEY_BACKUP` | — | Auto-switch on 402 (insufficient balance) |
| `PLANNER_BASE_URL` |  | API base URL |
| `PLANNER_MODEL` | `gemini-2.5-flash` | Model name as recognized by the API |

**Recommended models** (all tested via xinghuapi proxy):

| Model | Best for | Notes |
|-------|----------|-------|
| `gemini-2.5-pro` | Complex geopolitical / technical topics | Best structural decomposition |
| `gemini-2.5-flash` | Standard topics, cost-efficient | Default recommendation |
| `grok-4` | Topics with broad content latitude | Permissive content policy |
| `deepseek-v3.2-exp` | Budget-conscious usage | Strong Chinese-language planning |
| `gpt-5` | Maximum reliability | Higher cost |

### Query generation layer (`QUERY_*`)

Generates search queries for each web-researcher subagent. Same key structure as planner.

| Variable | Default |
|----------|---------|
| `QUERY_MODEL` | `deepseek-v3.2-exp` |

### Claude API (`ANTHROPIC_*`)

Used by Claude Code for the orchestrator and all subagents (Sonnet, Opus, Haiku).

```env
ANTHROPIC_API_KEY=sk-...
ANTHROPIC_BASE_URL=https://xinghuapi.com   # omit for direct Anthropic access
ANTHROPIC_API_KEY_BACKUP=sk-...            # for manual key rotation on 402
```

> **Note on 402 errors:** The Claude API key is loaded once at `claude` startup and cannot be hot-swapped mid-session. If you hit a 402 during a run, exit Claude Code, swap `ANTHROPIC_API_KEY` with your backup key in `.env`, and restart. A convenience swap script is included in `scripts/swap_key.sh`.

### Tavily search (`TAVILY_API_KEY_1` … `TAVILY_API_KEY_8`)

Up to 8 Tavily keys with automatic failover. The system cycles to the next key on 401/403/429 errors. Each web-researcher subagent can make up to 5 Tavily calls, so 8 concurrent researchers with 8 keys covers peak load comfortably.

---

## Project structure

```
.
├── .claude/
│   ├── agents/
│   │   ├── web-researcher.md     # Parallel search worker (Sonnet)
│   │   ├── gap-analyzer.md       # Coverage + red team auditor (Sonnet)
│   │   ├── synthesizer.md        # Report writer (Opus)
│   │   └── citation-agent.md     # Lightweight citation mapper (Haiku)
│   ├── commands/
│   │   └── deep-research.md      # /deep-research slash command (orchestrator)
│   ├── hooks/
│   │   ├── preflight_check.py    # Runs on /deep-research submit
│   │   ├── pre_write_check.py    # Blocks plan.md write before user confirms
│   │   ├── post_write_check.py   # Validates written files
│   │   ├── post_task_log.py      # Logs subagent completions
│   │   └── final_quality_gate.py # End-of-run quality check
│   └── settings.local.json       # Hook registration
│
├── scripts/
│   ├── _utils.py                 # Shared utilities (UTF-8, retry, sanitize, slug)
│   ├── init_slug.py              # Per-run slug and directory initializer
│   ├── llm_plan.py               # Research plan generator (OpenAI-compat)
│   ├── llm_queries.py            # Search query generator (OpenAI-compat)
│   ├── tavily_search.py          # 8-key failover Tavily wrapper
│   └── apply_citations.py        # Pure Python citation replacer (no LLM)
│
├── findings/
│   └── <slug>/                   # Per-run findings JSON files
│       ├── sub_a.json
│       ├── sub_b.json
│       └── ...
│
├── output/
│   ├── .current_slug             # Active slug (read by hooks)
│   └── <slug>/
│       ├── plan.md
│       ├── .plan_confirmed
│       ├── .quality_gate_state.json  # Per-run state (no cross-slug pollution)
│       ├── analysis.md
│       ├── report_draft.md
│       ├── citations_map.json
│       ├── report_final.md       # ← final deliverable
│       └── workflow.log
│
├── .env.example
├── requirements.txt
└── README.md
```

---

## Report format specification

The synthesizer produces reports in a consistent structure derived from studying Gemini Deep Research and Anthropic Claude Research output styles:

| Section | Content |
|---------|---------|
| **Title** | `Main Title: Subtitle` — subtitle must be a thesis statement, not a description |
| **Executive Summary** | 300–500 words. Core claim + 2–3 key data points + primary risk |
| **Introduction** | Time-context paragraph + thesis statement + scope definition |
| **Root Cause Analysis** | 3–5 subsections, each following: *facts → mechanism → trajectory* |
| **Comparative Analysis** | ≥3 tables: horizontal comparison, timeline, scenario probability matrix |
| **Forward Scenarios** | Base (60%) · Upside (20%) · Downside (15–20%) · Tail risk (<5%) + strategic recommendations |
| **Conclusion** | Core finding restated + research limitations + open questions |
| **References** | APA format · `(Author/Org, Year)` inline · full list with `Retrieved YYYY-MM` |

**Writing quality controls enforced by hook and prompt:**

- No vague quantifiers: "overwhelming majority" → specific percentage with source and date
- Vocabulary frequency caps: *structural* ≤5 uses, *paradox* ≤4, *deadlock* ≤3 per report
- Each major section uses a different analytical concept as its theoretical lens (no single framework repeated throughout)
- Adversarial perspectives explicitly represented with quantified counter-evidence, not dismissed in a single sentence

---

## Troubleshooting

### Plan is written before I see the options

The `pre_write_check` hook should block this. Verify it is registered in `.claude/settings.local.json` under `PreToolUse` and that Claude Code is loading it (check `claude --version` supports hooks).

### Citation agent keeps timing out

This is expected on very large reports. The v3 two-stage pipeline handles this: `apply_citations.py` runs regardless of whether the agent completed. Check `output/<slug>/report_final.md` — it will exist with either proper citations or the "APA pending" appendix listing all unresolved placeholders.

### 402 errors interrupting the run

This is an API balance issue with your provider, not a code bug. Options:
1. Swap to your backup key and restart: `python scripts/swap_key.sh && claude`
2. The planner/query scripts auto-switch to `*_BACKUP` keys on 402. Only the Claude main process key requires a restart.

### Findings files going to the wrong directory

Hooks read `output/.current_slug` to find the active run's directories. If this file is missing or stale, delete it and re-run from Phase 0.5. You can also set it manually: `echo "your_slug" > output/.current_slug`.

### Garbled output on Windows (GBK encoding errors)

All scripts call `setup_utf8()` from `_utils.py` at startup, which forces `stdout`/`stderr` to UTF-8. If you still see encoding errors, set these in your shell before launching Claude Code:

```cmd
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
```

Avoid piping Tavily output through inline `python -c "..."` commands on Windows — redirect to a temp file instead.

---

## How it relates to Anthropic's multi-agent research paper

This project is a direct implementation of the architecture described in Anthropic's [*How we built our multi-agent research system*](https://www.anthropic.com/research/multi-agent-research), with several practical additions:

| Anthropic principle | Implementation |
|---------------------|----------------|
| Orchestrator-worker with independent context windows | `.claude/agents/` native mechanism |
| Dynamic subagent spawning | Complexity-based 3–8 researchers, `max_parallel=5` batch control |
| Explicit delegation with five-component prompts | Task prompts contain: objective / output spec / tool guidance / hard limits / success criteria |
| Start wide then narrow | Built into `web-researcher.md` protocol and `llm_queries.py` mode selection |
| Separate CitationAgent pass | `citation-agent` + `apply_citations.py` two-stage pipeline |
| Evaluation through outcome, not path | `gap-analyzer` scores coverage, not compliance |

Additions beyond the paper:
- **Plan confirmation gate** — enforces human-in-the-loop at planning stage
- **Red team check** — `gap-analyzer` explicitly flags dimensions lacking adversarial evidence
- **Vocabulary quality controls** — prevents the "buzzword soup" failure mode in long-form synthesis
- **Slug-scoped file isolation** — multi-run reproducibility
- **Hook-enforced process contracts** — structural guarantees that LLM prompting alone cannot provide

---

## License

MIT License. See [LICENSE](LICENSE).

---

## Acknowledgements

Built on [Claude Code](https://claude.ai/code) by Anthropic. Research architecture inspired by Anthropic's multi-agent research system. Web search powered by [Tavily](https://tavily.com).
