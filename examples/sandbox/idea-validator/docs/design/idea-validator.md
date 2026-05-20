# Design — idea-validator — CLI UX brief and landing page wireframes

- **Status**: Draft (Designer agent; correlation `b85b54ff-a751-4cfb-a4ba-ab0fc81c9fc2`)
- **Canonical path**: `docs/design/idea-validator.md` (parent repo)
- **Sandbox mirror**: `examples/sandbox/idea-validator/docs/design/idea-validator.md` (this file)
- **Consumed by**: Frontend Developer implementing `apps/web/idea-validator/index.html`
- **References**: sandbox ADR-0001, parent ADR-0011, ADR-0012, ADR-0013

---

## Summary

Defines the visual language for both surfaces: a single-column static landing page (nav, hero with CLI sample, inline sample report, install CTA) and Rich-formatted CLI output (section rules, competitor table, severity-coloured risks, score panel). Shared design tokens bridge the two surfaces. Sign-up and idea-submission form are reserved as v3 scope per ADR-0013.

---

## Landing-page layout

```
═══════════════════════════════════════════════════════════════════
SURFACE 1 — LANDING PAGE  apps/web/idea-validator/index.html
  Max-width: 720 px, centered, 24 px side padding.
  Single column. No JavaScript. No external CSS/JS imports.
  Breakpoint: 768 px (mobile < 768 px, desktop ≥ 768 px).
═══════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────┐
│ <nav>  48 px top pad, border-bottom 1 px #E5E7EB        │
│  idea-validator           (--font-mono, --accent)        │
│                                     [Install →]          │
│                         (a[href=#install], button-style) │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ <section id="hero">  72 px top pad                      │
│                                                         │
│  Validate your product idea in seconds.                 │
│  (h1, --font-sans, --h1-size, font-weight 700, lh 1.2)  │
│                                                         │
│  Competitors · Market size · Top risks · Score 1–10     │
│  (p, --neutral, 1.1 rem, margin-top 12 px)              │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │ $ uv run idea-validator analyze \                 │  │
│  │       --idea "your product idea" --depth quick    │  │
│  └───────────────────────────────────────────────────┘  │
│  (pre, --font-mono, 0.85 rem, bg #F9FAFB,               │
│   border 1 px #E5E7EB, border-radius 6 px, 14 px pad)   │
│                                                         │
│  [→ Get started]  ← a[href="README.md#install"]         │
│  (display inline-block, bg --accent, color #fff,        │
│   padding 10 px 22 px, border-radius 6 px, no underline)│
│                                                         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ <section id="sample">  64 px top pad                    │
│                                                         │
│  Sample report                                          │
│  (h2, --font-sans, --h2-size, font-weight 600)          │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ <pre class="report">                            │   │
│  │   [verbatim content of sample/report.md]        │   │
│  │   Score line uses class="score score--warning"  │   │
│  └─────────────────────────────────────────────────┘   │
│  (pre: --font-mono, 0.8 rem, bg #F9FAFB,                │
│   border-left 4 px solid --accent, padding 16 px,       │
│   border-radius 0 4 px 4 px 0, overflow-x auto)         │
│                                                         │
│  Score color classes (apply to .score span):            │
│    .score--success { color: var(--success) }  ≥ 8       │
│    .score--warning { color: var(--warning) }  5–7       │
│    .score--error   { color: var(--error)   }  ≤ 4       │
│                                                         │
└─────────────────────────────────────────────────────────┘

<!-- v3 CTA placeholder — NOT rendered in v2:
┌─────────────────────────────────────────────────────────┐
│ <section id="signup"> [DEFERRED — v3 per ADR-0013]      │
│  Get notified when the hosted version launches.         │
│  [___your@email.com___________] [Notify me →]           │
│  Form target: ADR required before any implementation.   │
└─────────────────────────────────────────────────────────┘
-->

┌─────────────────────────────────────────────────────────┐
│ <footer>  32 px top pad, border-top 1 px #E5E7EB        │
│  MIT licence · GitHub                                   │
│  (--neutral, 0.85 rem)                                  │
└─────────────────────────────────────────────────────────┘
```

### Mobile breakpoint (< 768 px)

Applied via `@media (max-width: 767px)`:

- `--h1-size` becomes `1.75rem` (28 px).
- Side padding drops from 24 px to 16 px.
- `pre.report` gains `overflow-x: auto` and `font-size: 0.72rem` — scrolls horizontally rather than reflows (terminal column alignment is meaningful).
- The CTA button (`[→ Get started]`) becomes `width: 100%; text-align: center`.
- Nav: logo and CTA remain on one line (both are short enough at mobile widths); no hamburger needed.

---

## CLI output structure

```
═══════════════════════════════════════════════════════════════════
SURFACE 2 — CLI OUTPUT (Rich library)  stdout of `analyze`
  Printed via rich.console.Console(). No raw ANSI codes.
═══════════════════════════════════════════════════════════════════

╔══════════════════════════════════════════════════╗
║  idea-validator report                           ║  Panel(title=…, style="bold", border_style="bright_magenta")
╚══════════════════════════════════════════════════╝

Idea:  AI tutoring marketplace                         [dim]
Depth: quick · Generated: 2026-01-01T00:00:00          [dim]

──── Competitors ──────────────────────────────────  Rule(title="Competitors", style="dim")
┌─────────────────────┬───────────────┬────────────────────┐
│ Name                │ URL           │ Positioning        │  header bold + bright_magenta
├─────────────────────┼───────────────┼────────────────────┤
│ Wyzant              │ wyzant.com    │ Tutor marketplace  │
│ Chegg Tutors        │ chegg.com     │ Study-help         │
└─────────────────────┴───────────────┴────────────────────┘
  Table(box=SIMPLE_HEAD, header_style="bold bright_magenta", show_lines=False)
  Max column widths: Name 24, URL 30, Positioning 40 chars.

──── Market Estimate ──────────────────────────────  Rule(title="Market Estimate", style="dim")
  TAM [bold]$12 B[/]  ·  SAM [bold]$3 B[/]  ·  SOM [bold]$150 M[/]
  [dim]Reasoning:[/dim] [paragraph text, wrapped at 72 chars]

──── Risks ────────────────────────────────────────  Rule(title="Risks", style="dim")
  [bold red]    ● HIGH  [/]  Regulatory compliance
  [bold yellow] ● MEDIUM[/]  Tutor supply constraint
  [bold green]  ● LOW   [/]  Payment processing complexity
  (severity keyword left-padded to 6 chars for alignment)

──── Differentiators ──────────────────────────────  Rule(title="Differentiators", style="dim")
  [bright_magenta]✦[/]  AI-powered matching
  [bright_magenta]✦[/]  Curriculum-aligned sessions
  [bright_magenta]✦[/]  Session recording & replay

──── Score ────────────────────────────────────────  Rule(title="Score", style="dim")
┌──────────────────────────────────────────────────┐
│  [bold score-color]7 / 10[/bold]                 │  Panel(box=ROUNDED)
│  market: 7  differentiation: 8  risk: 6   [dim]  │
│  [rationale, wrapped at 66 chars]                │
└──────────────────────────────────────────────────┘
  score-color mapping: green if ≥8, yellow if 5–7, red if ≤4
```

### Section-header conventions

- Rule title: `Title Case`, one word or short phrase (`"Competitors"`, `"Market Estimate"`, `"Top Risks"`).
- Rule style: `"dim"` (gray separator line, does not compete with content).
- Loud items: score number (bold + score-color), TAM/SAM/SOM values (bold), HIGH severity label (bold red).
- Quiet items: reasoning prose (dim), timestamps (dim), output file paths (dim).

---

## Web translation

> Machine-readable contract for `apps/web/idea-validator/index.html`.
> Frontend **MUST** define all seven custom-property names in `:root { … }`.
> Designer values below are authoritative; Frontend supplies hardcoded fallbacks
> that these values override. The verbatim heading "Web translation" allows
> Frontend to locate this section programmatically.

### Color tokens

```css
--accent:  #7C6AF7;   /* warm violet — headers, CTAs, rule titles, score accent  */
--success: #22C55E;   /* green       — score ≥ 8, LOW severity, differentiators  */
--warning: #F59E0B;   /* amber       — score 5–7, MEDIUM severity                */
--error:   #EF4444;   /* red         — score ≤ 4, HIGH severity, stage failures  */
--neutral: #6B7280;   /* gray        — meta text, labels, reasoning prose (dim)  */
```

### Typography tokens

```css
--font-mono: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
--font-sans: 'Inter', system-ui, sans-serif;
```

### Heading-size tokens

```css
--h1-size: 2rem;    /* 32 px at 16 px root — hero headline                        */
--h2-size: 1.4rem;  /* 22 px at 16 px root — section title (e.g. "Sample report") */
```

---

## Annotated example (CLI rendering)

Canonical Pydantic field names from `models.py` are annotated with `← fieldname`.
No aliases. Severity values are lowercase strings (`"high"`, `"medium"`, `"low"`).

```
$ idea-validator analyze --idea "AI tutoring marketplace" --depth standard

──── Competitors ──────────────────────────────────────────────────────────

  Name            │ URL               │ Positioning
  ────────────────┼───────────────────┼────────────────────────────────────
  Wyzant          │ wyzant.com        │ Tutor marketplace
  Chegg Tutors    │ chegg.com         │ Study-help + textbooks
  Preply          │ preply.com        │ Language tutoring
  TutorMe         │ tutorme.com       │ 24/7 on-demand tutoring

──── Market Estimate ──────────────────────────────────────────────────────

  TAM  $12,000,000,000   ← tam_usd (int, USD)
  SAM   $3,000,000,000   ← sam_usd (int, USD)
  SOM     $150,000,000   ← som_usd (int, USD)

  Reasoning: [dim] The private tutoring market is large and growing.
  AI-assisted matching reduces acquisition cost, which expands SAM.

──── Risks ────────────────────────────────────────────────────────────────

  ● HIGH    Regulatory compliance          ← severity = "high"   (--error)
  ● MEDIUM  Tutor supply constraint        ← severity = "medium" (--warning)
  ● LOW     Payment processing complexity  ← severity = "low"    (--success)

──── Differentiators ──────────────────────────────────────────────────────

  ✦  AI-powered matching
  ✦  Curriculum-aligned sessions
  ✦  Session recording & replay

──── Score ────────────────────────────────────────────────────────────────

  7 / 10   ← score (int, 1–10)
  Components: market=7  differentiation=8  risk=6   ← components dict
  [Rationale prose wrapped at 72 chars…]
```

---

## Decisions

### Sign-up form and idea-submission form: deferred to v3

**Choice**: Landing page is read-only in v2. A commented-out v3 placeholder block marks the reserved position in the layout above.

ADR-0013 resolves the PM-flagged ambiguity: the v2 spec says "links to CLI install instructions" only. The TL task assignment mentions sign-up and submission, but the spec chain wins. A third-party form target (Formspree, mailto, or new API surface) requires its own ADR before Frontend can implement it safely; that scope cannot land in iter-3 without adding DevOps and privacy decisions outside this iteration's budget.

### Single-column layout, 720 px max-width

**Choice**: One column, centered, no sidebar, no grid.

The pre-formatted CLI sample report and competitor table need horizontal room and wrap badly in narrow columns. A single 720 px column is wide enough for the table, narrow enough to read on a 13-inch laptop, and requires zero responsive-breakpoint CSS — keeping the page under 80 lines. Mobile merely reduces padding and font size; no column rearrangement needed.

### Rich library for CLI formatting over raw ANSI codes

**Choice**: Use Rich `Console`, `Table`, `Rule`, `Panel`, and `Markup` throughout.

Rich is already a natural companion to Click (same ecosystem, no version conflicts) and gives Tables, Rule dividers, and Panels with one import. Raw ANSI codes would duplicate that work, produce unreadable string literals, and break on Windows terminals that Rich already handles.

### Sample report embedded verbatim as `<pre>` content

**Choice**: Frontend copies `sample/report.md` text into a `<pre class="report">` block at HTML-write time; no JavaScript fetch.

ADR-0012 pins `sample/report.md` as the Backend→Frontend handoff artifact. Embedding verbatim keeps the page self-contained (opens as `file://`), auto-updates when Backend re-runs `scripts/refresh_sample.sh` and commits the result, and preserves the CLI visual language without re-rendering.

### Accent color #7C6AF7 (warm violet) for both surfaces

**Choice**: `#7C6AF7` in CSS; `bright_magenta` in Rich (closest standard terminal color).

Violet reads as "analytical and intelligent" without the medical/alert connotation of red or the finance-SaaS connotation of dark blue. The warm shift off pure purple distinguishes it from GitHub (`#6E40C9`) and Linear (`#5E6AD2`) at a glance. `bright_magenta` is the closest Rich built-in that renders consistently across dark and light terminal themes.

### Score color as CSS class (not inline style) on the landing page

**Choice**: Wrap the score number in `<span class="score score--warning">` (or `--success` / `--error`). Classes map to CSS custom properties.

The sample report is static, so only one score class appears in v2 HTML. But using a class instead of an inline color means a Designer can reskin all score badges by editing two lines of CSS rather than grepping HTML. Consistent with the CLI's runtime color logic, which uses the same three severity levels.

### Mobile: `overflow-x: auto` on `<pre>` rather than reflow

**Choice**: The sample report `<pre>` block scrolls horizontally on narrow viewports instead of wrapping.

The CLI output uses column alignment (e.g. competitor table, risk severity padding). Reflow breaks that alignment and makes the output unreadable. Horizontal scroll is the correct treatment for pre-formatted terminal output on mobile; it matches how GitHub renders `<pre>` and is what experienced CLI users expect.

---

## Constraints for Frontend (summary)

1. All seven custom-property names (`--accent`, `--success`, `--warning`, `--error`, `--neutral`, `--font-mono`, `--font-sans`) MUST appear in `:root { … }` in `index.html`; Frontend may change fallback hex values but not the names.
2. `<pre class="report">` MUST have `overflow-x: auto` — terminal column alignment must not reflow on mobile.
3. The score badge span uses CSS classes (`.score--success`, `.score--warning`, `.score--error`), not inline styles.
4. Single self-contained HTML5 file, ≤ ~80 lines of CSS in `<style>`, no `<script>` tags.
5. Desktop layout is single-column at max-width 720 px. No two-column grid.
6. Mobile breakpoint: `@media (max-width: 767px)` — reduce `--h1-size` to 1.75rem, reduce side padding to 16 px, make CTA full-width.
7. Do NOT add animation, transitions beyond simple `:hover { opacity: 0.85 }` on the CTA. The page is a developer tool; understated is correct.
8. Body background: `#FFFFFF`. Body text: `#111827`. Pre/code background: `#F9FAFB`. Border color: `#E5E7EB`. Do not deviate without a Designer PR.

---

## References

- examples/sandbox/idea-validator/docs/adr/0001-idea-validator-v2-architecture.md
- docs/adr/0011-idea-validator-v2.md
- docs/adr/0012-idea-validator-v2-target-repo-and-sample-generator.md
- docs/adr/0013-idea-validator-v2-persistence-and-scope.md
- docs/backlog/idea-validator.md
- examples/sandbox/idea-validator/backlog.md
- docs/sandbox/idea_validator_v2_spec.md
