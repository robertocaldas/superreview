---
name: superreview
description: Draws an interactive change diagram of code changes as a self-contained HTML page — boxes are files/classes, arrows are calls between them, colour marks added/modified/deleted, hovering explains what changed and why, and clicking a link in the panel opens that exact line in the reader's own editor. Use this whenever the user wants to see, visualise, diagram, map, review or "get a picture of" what changed — their uncommitted work by default, or a pull/merge request, a commit range, a branch diff, a whole repo, or the files a plan document proposes to touch — even when they don't say the word "diagram".
---

# superreview — interactive change diagrams

Turn a set of **changes** (additions, deletions, modifications) into a single
self-contained HTML diagram: boxes are code elements, arrows are calls between
them, colour is the kind of change, hover shows what changed and why.

## Requirements

`d2` on PATH and the bundled `scripts/build.py`; `assets/wrapper.html` is the page template it fills (`brew install d2` / `winget install terrastruct.d2`) and `python3`.
If `d2` is missing, say so and stop — do not hand-draw an SVG.

## 1. Decide the scope

| The user said | Source of changes |
|---|---|
| *(nothing — the default)* | `git status --short` + `git diff HEAD` — the working tree |
| "since/between commits" | `git diff A..B` |
| "branch X vs Y" | `git diff Y...X` |
| a pull/merge request | Its branch diff: `git fetch` the base and head refs, then `git diff base...head`. A forge CLI is a shortcut where one is installed and authenticated — `gh pr diff N` / `glab mr diff N`, plus `gh pr view` / `glab mr view` for the title and description |
| "the whole repo" | Every tracked source file; everything is `unchanged` except what the user calls out |
| "this plan" + a document | The document is the **input**: nodes are the files it proposes to touch |

## 2. Collect the changes

Run the diff with enough context to say *what* and *why*
(`git diff -U3`, plus `git show`/`cat` on new files). Then:

**Include** every changed source file, plus unchanged files that are needed to
make the picture readable (callers/callees of what changed).
**Exclude**
- anything git ignores — never inspect or list it (`git status` already respects
  `.gitignore`; for whole-repo scope use `git ls-files`),
- documentation files (`*.md`, `docs/**`, changelogs, `LICENSE`) — with one
  exception: a plan/requirements document *used as the source* for the diagram is
  not a node in it either, it is the input,
- lockfiles and generated code.

**Binaries** (images, prefabs, scenes, `.asset`, audio, models) **are included** —
they are real changes — but set `"clickable": false` on them, since an editor
cannot usefully open them at a line.

## 3. Write the graph JSON

Write it to a temp path (the scratchpad), not into the project.

```json
{
  "title":    "Short name of the change set",
  "subtitle": "N modified · N added · +X / -Y lines",
  "source":   "code · a1b2c3d..e4f5a6b (12 commits)",   // required — see below
  "root":     "/absolute/path/to/repo",
  "groups":   [{ "id": "core", "label": "src/core" }],
  "nodes": [{
    "id":     "src/core/thing.cs",       // repo-relative path — also the identity
    "label":  "Thing",                   // what the box says
    "kind":   "service",                 // free text: class, MonoBehaviour, prefab, endpoint…
    "group":  "core",
    "parent": "src/core/host.cs",       // optional — draws this box inside that one
    "status": "added | modified | deleted | unchanged",
    "clickable": true,
    "changes": [{ "line": 42, "what": "…", "why": "…", "diff": "@@ -40,3 +40,4 @@\n+…" }]
  }],
  "edges": [{
    "from": "src/core/a.cs", "to": "src/core/b.cs",
    "status": "added | modified | deleted | unchanged",
    "changes": [{ "call": "Foo()", "line": 42, "path": "src/core/a.cs", "what": "…", "why": "…",
                  "diff": "@@ -40,3 +40,4 @@\n+    b.Foo();" }]
  }]
}
```

### `source` — what the diagram was built from

Required. It prints in the page header, so a reader opening the file weeks later
can tell what they are looking at without asking. Say **which kind of input** it
was and **exactly which revision**:

| Scope | `source` |
|---|---|
| working tree | `code · working tree, uncommitted (HEAD a1b2c3d)` |
| one commit | `code · commit a1b2c3d "message"` |
| a range | `code · a1b2c3d..e4f5a6b (12 commits)` |
| branch diff | `code · feature-x vs main (merge-base a1b2c3d)` |
| pull/merge request | `code · PR #418 "title" — head e4f5a6b onto main a1b2c3d` |
| whole repo | `code · full tree at a1b2c3d` |
| a plan document | `plan · Docs/crew-behaviour.md (not yet implemented)` |

Get the hashes from git (`git rev-parse --short HEAD`), never from memory. If
the working tree is dirty while diagramming a commit, say so — it changes what a
reader will find when they open the files.

### Colour rules — two levels, and they do not mean the same thing

Everything here turns on one distinction: *the file* versus *the content inside
it*. A file that gains three new lines was **modified as a file**, but those three
lines are **additions**. Mixing the two levels is the single easiest way to make
the diagram lie.

**A box is a file**, so its `status` describes what happened to the file:

- `added` — green — the file is **brand new**.
- `modified` — dark yellow — the file existed and its contents changed, in any
  way at all. Yellow is the umbrella: it says "this file changed" without
  claiming the change was an addition or a removal. **A box is never red.**
- `deleted` — grey, dashed — the file is gone.
- `unchanged` — black outline — context only.

**A `changes` entry, and an arrow, is content**, so its `status` describes what
happened to those lines:

- `added` — green — new lines, a new member, a call that did not exist before.
- `modified` — **red** — lines that existed and were rewritten.
- `deleted` — grey — lines or a call that were removed.

So a file whose diff is purely `+` lines is a **yellow box** containing **green
changes**. Do not mark those changes `modified` just because the file is; that is
the mistake this section exists to prevent.

**A change already shown by an arrow does not colour the box.** If all that
happened to a file is that a call to or from it appeared, the arrow carries that
colour and the box stays black. Colour the box only when the file has *other*
changes of its own.

### Nesting — the relation that costs no arrow

`parent` draws a box **inside** another box. Use it whenever one element
contains another — hosts, owns, declares, or is the base type of. Containment is
two-dimensional, so spending a full-width arrow on it wastes the page on
something the layout can show at a glance.

It pays twice: callers that reach *into* the container become short local arrows
instead of crossings, and several arrows to different children can collapse into
one arrow at the container.

- A box has one `parent`, so when an element is both contained and derived, nest
  by whichever fact the review turns on and put the other in `kind`
  (`"duty · extends Duty"`). That line costs no layout.
- Children keep their own status colour; a container takes a pale tint of its
  own, so a container full of same-status children is not one block of colour.
- Nested boxes have their own arrows — sibling to sibling, child to anything
  outside, outside into a child, at any depth. Only the containment is not an
  arrow.
- An arrow between children of two *different* containers is the most expensive
  to route, since it has to leave one box and enter another. Accept the cost.
  **Never move an arrow's endpoint to a container to tidy the picture** — an
  arrow ends where the call lands, and retargeting it at the parent states
  something the code does not do. Point at a container only when the caller
  really does address the container itself.
- Nesting has a cost of its own: members are packed together, so a box that
  would otherwise sit near the thing it talks to can be dragged far from it.
- `group` is ignored on a node that has a `parent`.

### Groups

A group is a layout constraint, not decoration: it packs its members together,
so a flow that enters and leaves a group forces the return trip around the whole
container. Group only when the boundary is itself something the reviewer needs
to know — that these files ship together, that this is the layer being replaced.
Not everything needs one; when the reader would learn nothing from the boundary,
leave it out, since the folder path is already in the box title and the hover
card. When you do group, make the group a layer in the flow — entering on one
side, leaving on the other — rather than a directory listing whose members sit
on both sides.

### Arrow rules

An arrow is an **interaction**, not a change to the thing it points at. Describe
what the source *does* to the target — "reads FakePerspectiveYawStrength",
"calls Save()", "subscribes to OnHit" — in the present tense. Writing "adds two
fields" on an arrow describes the target's own diff, which the target's box
already covers, and leaves the reader with no idea what the two files have to do
with each other.

Each entry's `line` and `path` must be **the same place**: the call site in the
source file. A reader clicking a line number on an arrow expects to land on the
line that performs the interaction, not on the declaration at the other end. If
you want to point at the declaration too, that belongs in the target box's own
`changes`, with that file's path and line.


- One arrow per `(from, to, status)`. Two calls between the same pair with
  **different** statuses ⇒ **two arrows**.
- Each direction is its own arrow — never a double-headed one.
- Thickness grows with the number of changes on it (handled by `build.py`).
- Label: a **single** change shows the call name; **several** show `x2`, `x3`, …
  (handled by `build.py` — just supply one entry per call in `changes`).

### Hover text rules

Each entry in `changes` becomes one block in the hover card, divided by a rule.
Keep each one **concise** — one line of *what*, one of *why*:

- `line` — the line number, when there is a meaningful one (omit for binaries).
  Verify it — `grep -n` the symbol rather than counting hunk headers, which give
  the position of the hunk, not of the line you are describing.
- `path` — optional; defaults to the element's own path. Set it only to point at
  a *different* file, and then the `line` must be a line in *that* file.
- `diff` — the unified hunk for this change, as plain text with its
  `@@` header and `+`/`-` prefixes. The page has a **diff** checkbox that reveals
  it inside the card, which is as close as a browser can get to an IDE's diff
  view — no editor exposes one over a URL scheme. Keep each hunk to the few lines
  that matter (`git diff -U2` on that file, then take the relevant hunk); a whole
  file pasted in makes the card unreadable. Give one to every change, on boxes
  and on arrows. Omit it only where there is nothing to show: binaries, a change
  with the status `unchanged`, or a diagram built from a plan. `build.py` prints
  a warning for each other change that has a `line` and no `diff`.

  On an arrow, the hunk shows the call site. That is the lines in the calling
  file that add, change or remove the call. The calling file is `path` when you
  set it, and `from` when you do not. The lines inside the called method go on
  the box of the called file.

  The hunk has to show **the lines the entry is actually about** — after writing
  it, read it back and check the symbols named in `what` appear in it. Slicing
  blindly around `line` is how a card ends up claiming "mouse drag moves the
  ship" above a hunk of the method signature and an unrelated comment, which
  tells the reader nothing and costs you their trust in the rest of the page.
  New files have no diff at all, so pick the range yourself and label it
  `@@ new file, lines A-B @@`; anchor `line` to the line the text describes,
  not to the top of the enclosing method.

  Cut the range on syntactic boundaries. A hunk that opens on the last line of a
  comment block, or on the closing brace of the statement above, reads as a
  fragment of someone else's sentence and makes the reader distrust the card.
  Start at the statement (or at the whole comment, if the comment is the point)
  and end where it ends.
- `status` — optional, per change. A modified file often holds an addition and a
  removal at once; giving each entry its own status makes each one show the right
  coloured square. Omit it and the entry inherits the element's status.
- `what` — what the change is. `why` — why it was made.
- Clicking an element pins its card; in the pinned card the title and every line
  number are links that open the file at that line in the reader's editor.

### Ordering the changes

The order of `changes` is the order the reader meets them, and `build.py` keeps
your array order exactly, so it is a real editorial decision rather than a
formatting detail.

Ask first whether the entries are **related** — whether one has to be understood
before the next makes sense (a field is declared, then read, then written back;
a guard is added, then the thing it guards). If they are, order them the way you
would explain them to someone seeing the file for the first time: the change that
establishes the idea, then the ones that build on it, regardless of where they
sit in the file. Reading them top to bottom should teach the change.

If they are **independent** — several unrelated edits that happen to share a file
— there is no story to tell, so order them by line number. That way the reader
can scan the card against the file without hunting.

Do not rank by importance. "Most significant first" reads as a summary and buries
whatever context the rest needed to make sense.

## 4. Build

```bash
mkdir -p <repo>/docs/superreview
python3 <skill>/scripts/build.py <graph.json> \
        <repo>/docs/superreview/$(date +%Y-%m-%d-%H-%M)-<mnemonic>.html
```

`build.py` warns on stderr when an element gets no hover target, when a `parent`
does not name a node, and when a nested node's `group` is discarded. Fix those
before handing the page over — an unbound element is dead on the page.

`root` is the only machine-specific value in the JSON — it is the absolute path
used to build editor links. Leave `editor` out: the page ships a picker (system
default, VS Code, Cursor, Rider, IntelliJ, WebStorm, PyCharm, Sublime, Zed) that
each viewer sets for themselves, remembered in their browser. Set `"editor"` only
to change the initial choice for a team that all uses one IDE.

`<mnemonic>` is a short kebab-case name for the change set (`fake-perspective`,
`auth-refactor`). The date/time is **now**. `build.py` links the new page back to
the newest earlier file in that folder automatically — pass `"prev"` in the JSON
only to override it.

## 5. Re-runs

Running the skill again **always writes a new `.html` and `.d2`**, under a new
timestamp, even when nothing in the code has changed since the last one. Never
overwrite an earlier file, and never stop with "nothing changed" — the earlier
reports are a record of what was reviewed and when, and `build.py` links each
new page back to the previous one.

Read the most recent report for that repo first (its `.d2` and the `changes`
text in its `.html`) and **carry the wording forward verbatim** for anything
that has not changed. Rephrasing a stable explanation each run is noise: it
makes the two pages look different when the code is not, and it costs the
reader the ability to spot what actually moved by comparing them. Write new
prose only for what is genuinely new or different, and let `source` show which
revision each page covers.

## 6. Report

Give the user the path, and one line on what the diagram shows. The HTML is
self-contained: hover for detail, click to zoom and pin, click a link in the
pinned panel to open that line, drag or scroll to pan, pinch or ⌘-scroll to
zoom, Esc to close.

If the page was not published, end with one line offering to publish it.

## 7. Publish (optional)

Publish only when the user asks for a link, or asks to share or publish the
diagram — the page carries the repo's absolute path (`root`) and every diff
hunk, so never publish it unasked.

Publish the `.html` that `build.py` just wrote with the Artifact tool:
`file_path` is that file, `icon` is `diagram`, `description` is the `source`
line. Publish the page as built; do not hand-edit it for the host. Each run
writes a new file, so each run gets its own URL — the same rule as §5: an
earlier report is never overwritten. Give the user the URL next to the local
path.

On the hosted page:

- The `← previous` link points at a file on disk, so the page drops it. To keep
  the chain, set `"prev"` in the JSON to the previous report's artifact URL
  before building; an absolute link is kept.
- Editor links still open `root` on the viewer's machine, so they work only for
  someone with the repo checked out at that same path.
