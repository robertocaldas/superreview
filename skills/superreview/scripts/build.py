#!/usr/bin/env python3
"""Build an interactive change diagram from a graph.json.

  python3 build.py graph.json out/2026-08-31-14-02-fake-perspective.html

Pipeline: graph.json -> d2 text -> (d2 --layout=elk) -> svg
          -> inlined into wrapper.html together with a metadata map keyed by
             the base64 group class d2 stamps on every node and edge.
"""
import base64, html, json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

# status -> (fill, stroke, font)           boxes
NODE_STYLE = {
    "added":     ("#DCFCE7", "#16A34A", "#14532D"),
    "modified":  ("#FEF3C7", "#B45309", "#78350F"),
    "deleted":   ("#F2F2F2", "#C0C0C0", "#8A8A8A"),
    "unchanged": ("#FFFFFF", "#111827", "#111827"),
}
# a box that holds other boxes gets the pale tint, so its children stay legible
# against it instead of merging into one block of colour
CONTAINER_FILL = {
    "added": "#F0FDF4", "modified": "#FFFBEB",
    "deleted": "#F7F7F7", "unchanged": "#FFFFFF",
}
# status -> stroke                         arrows
EDGE_STYLE = {
    "added":     "#16A34A",
    "modified":  "#DC2626",
    "deleted":   "#C0C0C0",
    "unchanged": "#111827",
}


def b64(s):
    return base64.b64encode(s.encode()).decode()


def q(s):
    return '"%s"' % str(s).replace('"', '\\"')


def d2_label(s):
    return str(s).replace('"', "'").replace("\n", "\\n")


def warn(msg):
    sys.stderr.write("warning: %s\n" % msg)


NUM = r'(-?[\d.]+)'


def unmask_labels(svg):
    """Swap d2's label mask for boxes painted behind the edge labels.

    d2 cuts the gap under each edge label by masking every connection with a
    diagram-sized mask. Browsers re-render that mask for each line on every
    frame, at the current zoom, so panning a zoomed-in diagram crawls. A box in
    the colour of whatever sits under the label looks the same and costs
    nothing. One difference: a later edge's line crossing an earlier label now
    draws over it, where the mask would have cut it.
    """
    boxes = []
    for m in re.findall(r'<mask\b.*?</mask>', svg, re.S):
        boxes += re.findall(r'<rect x="%s" y="%s" width="%s" height="%s" fill="black"'
                            % (NUM, NUM, NUM, NUM), m)
    svg = re.sub(r'<mask\b.*?</mask>', '', svg, flags=re.S)
    svg = re.sub(r' mask="url\(#[^)]*\)"', '', svg)

    # Every filled rect a label could sit on: the diagram background,
    # containers and boxes. The smallest one under a label is what shows there.
    under = [(float(x), float(y), float(w), float(h), fill) for x, y, w, h, fill in re.findall(
        r'<rect x="%s" y="%s" width="%s" height="%s"[^>]*?fill="(#[0-9A-Fa-f]+)"'
        % (NUM, NUM, NUM, NUM), svg)]

    def fill_at(cx, cy):
        hits = [r for r in under if r[0] <= cx <= r[0] + r[2] and r[1] <= cy <= r[1] + r[3]]
        return min(hits, key=lambda r: r[2] * r[3])[4] if hits else "#FFFFFF"

    left = list(boxes)

    def add_box(m):
        x, y = float(m.group(1)), float(m.group(2))
        for b in left:
            bx, by, bw, bh = map(float, b)
            if abs(bx + bw / 2 - x) < 1 and by <= y <= by + bh:
                left.remove(b)
                return ('<rect x="%s" y="%s" width="%s" height="%s" fill="%s"/>'
                        % (b + (fill_at(bx + bw / 2, by + bh / 2),)) + m.group(0))
        return m.group(0)

    svg = re.sub(r'<text x="%s" y="%s"[^>]*class="text-italic"' % (NUM, NUM), add_box, svg)
    for b in left:
        warn("no edge label found for the label gap at x=%s y=%s" % b[:2])
    return svg


def emit_d2(graph):
    nodes = graph["nodes"]
    by_id = {n["id"]: n for n in nodes}
    alias = {n["id"]: "n%d" % i for i, n in enumerate(nodes)}
    groups = {g["id"]: g for g in graph.get("groups", [])}

    # A node's container is its `parent` node if it has one, otherwise its
    # `group`. Containment is the one relation that costs no arrow, so a
    # hosts/owns/declares/extends relation belongs here rather than in `edges`.
    kids, roots = {n["id"]: [] for n in nodes}, {}
    for n in nodes:
        p = n.get("parent")
        if p is not None and p not in by_id:
            warn("node %s: parent %r is not a node — ignored" % (n["id"], p))
            p = None
        if p == n["id"]:
            warn("node %s: parent is itself — ignored" % n["id"])
            p = None
        if p:
            if n.get("group") and n["group"] != by_id[p].get("group"):
                warn("node %s: nested in %s, so its group %r is ignored"
                     % (n["id"], p, n["group"]))
            kids[p].append(n)
        else:
            roots.setdefault(n.get("group") or "", []).append(n)

    def ancestry(n):
        chain, cur, guard = [alias[n["id"]]], n, 0
        while cur.get("parent") in by_id:
            cur = by_id[cur["parent"]]
            chain.append(alias[cur["id"]])
            guard += 1
            if guard > len(nodes):
                sys.exit("error: parent cycle at %s" % n["id"])
        return chain, cur

    paths = {}
    for n in nodes:
        chain, top = ancestry(n)
        g = top.get("group") or ""
        if g:
            chain.append(g)
        paths[n["id"]] = ".".join(reversed(chain))

    def node_block(n, indent):
        pad = " " * indent
        ch = kids[n["id"]]
        status = n.get("status", "unchanged")
        fill, stroke, font = NODE_STYLE[status]
        if ch:
            fill = CONTAINER_FILL[status]
        label = d2_label(n["label"])
        if n.get("kind"):
            # a container's label sits on its top edge, so keep it to one line
            label += (" · " if ch else "\\n") + d2_label(n["kind"])
        out = ["%s%s: %s {" % (pad, alias[n["id"]], q(label)),
               "%s  style.fill: %s" % (pad, q(fill)),
               "%s  style.stroke: %s" % (pad, q(stroke)),
               "%s  style.font-color: %s" % (pad, q(font)),
               "%s  style.stroke-width: 2" % pad]
        if status == "deleted":
            out.append("%s  style.stroke-dash: 4" % pad)
        for c in ch:
            out += node_block(c, indent + 2)
        out.append("%s}" % pad)
        return out

    lines = ["direction: right", ""]
    for g, members in roots.items():
        if not g:
            for n in members:
                lines += node_block(n, 0)
            continue
        lines += ["%s: %s {" % (g, q(d2_label(groups.get(g, {}).get("label", g)))),
                  '  style.fill: "#FAFAFA"',
                  '  style.stroke: "#D8D8D8"',
                  '  style.font-color: "#6B7280"']
        for n in members:
            lines += node_block(n, 2)
        lines.append("}")
    lines.append("")

    # One arrow per (from, to, status). A pair whose changes have two different
    # statuses gets two arrows, and each direction is always its own arrow —
    # never a double-headed one.
    buckets = {}
    for e in graph["edges"]:
        for end in ("from", "to"):
            if e[end] not in paths:
                sys.exit("error: edge %s -> %s: %r is not a node"
                         % (e["from"], e["to"], e[end]))
        key = (e["from"], e["to"], e.get("status", "unchanged"))
        b = buckets.setdefault(key, [])
        b += e.get("changes") or [{"call": e.get("label", ""), "what": e.get("details", "")}]

    seen, meta = {}, {}
    for (src, dst, status), changes in buckets.items():
        sp, dp = paths[src], paths[dst]
        idx = seen.get((sp, dp), 0)
        seen[(sp, dp)] = idx + 1
        calls = len(changes)
        # one change: name the call on the arrow; more: just the count
        label = d2_label(changes[0].get("call", "")) if calls == 1 else "x%d" % calls
        stroke = EDGE_STYLE[status]
        lines += ["%s -> %s: %s {" % (sp, dp, q(label)),
                  "  style.stroke: %s" % q(stroke),
                  "  style.stroke-width: %d" % min(2 + (calls - 1) * 2, 10),
                  "  style.font-color: %s" % q(stroke)]
        if status == "deleted":
            lines.append("  style.stroke-dash: 4")
        lines.append("}")

        # d2 scopes an edge to the deepest container both ends share:
        # "a.b.(c -> d)[i]", and writes it out in full when they share none.
        a, b = sp.split(".")[:-1], dp.split(".")[:-1]
        common = []
        for x, y in zip(a, b):
            if x != y:
                break
            common.append(x)
        pre = ".".join(common)
        if pre:
            key = "%s.(%s -&gt; %s)[%d]" % (pre, sp[len(pre) + 1:], dp[len(pre) + 1:], idx)
        else:
            key = "(%s -&gt; %s)[%d]" % (sp, dp, idx)
        meta[b64(key)] = {
            "kind": "edge", "status": status,
            "title": "%s  →  %s" % (src.split("/")[-1], dst.split("/")[-1]),
            "sub": "%d change%s · %s" % (calls, "" if calls == 1 else "s", status),
            "path": src, "clickable": bool(graph.get("root")),
            "changes": changes,
        }

    for n in nodes:
        ch = n.get("changes") or ([{"what": n["details"]}] if n.get("details") else [])
        meta[b64(paths[n["id"]])] = {
            "kind": "node", "status": n.get("status", "unchanged"),
            "title": n["id"],
            "sub": " · ".join(filter(None, [n.get("kind"), n.get("status")])),
            "path": n["id"],
            "clickable": bool(graph.get("root")) and n.get("clickable", True),
            "changes": ch,
        }
    return "\n".join(lines) + "\n", meta


def main():
    src = sys.argv[1]
    dst = sys.argv[2]
    graph = json.load(open(src))
    d2_text, meta = emit_d2(graph)

    tmp = tempfile.mkdtemp()
    d2f, svgf = os.path.join(tmp, "d.d2"), os.path.join(tmp, "d.svg")
    open(d2f, "w").write(d2_text)
    subprocess.run(["d2", "--layout=elk", "--pad=40", d2f, svgf], check=True)
    svg = open(svgf).read()
    svg = unmask_labels(svg[svg.index("<svg"):])

    # Every hover card is bound by the base64 class d2 stamps on its shape. If a
    # key we generated is not in the SVG, that element is silently dead on the
    # page, so say so rather than shipping a diagram that does not respond.
    stamped = set(re.findall(r'class="([^"]*)"', svg))
    stamped = {c for group in stamped for c in group.split()}
    missing = [k for k in meta if k not in stamped]
    for k in missing:
        warn("no hover target for %s (%s)"
             % (meta[k]["title"], base64.b64decode(k).decode("utf-8", "replace")))

    prev = graph.get("prev")
    if prev is None:                                   # auto: newest earlier file in the same dir
        d, me = os.path.dirname(os.path.abspath(dst)), os.path.basename(dst)
        sib = sorted(f for f in os.listdir(d) if f.endswith(".html") and f < me) if os.path.isdir(d) else []
        prev = sib[-1] if sib else ""
    nav = ('<a class="nav" href="%s">← previous</a>' % html.escape(prev)) if prev else \
          '<span class="nav off">no previous diagram</span>'

    # What the reader is looking at: a plan document or real code, and exactly
    # which revision of it. Without this a diagram cannot be trusted a week later.
    source = graph.get("source")
    if not source:
        sys.exit("error: graph.json needs \"source\" — what the diagram was built "
                 "from (a plan document, or a commit / range / the working tree)")
    src_html = '<div class="src">%s</div>' % html.escape(source)

    wrapper = open(os.path.join(HERE, "..", "assets", "wrapper.html")).read()
    out = (wrapper
           .replace("<!--{{TITLE}}-->", html.escape(graph.get("title", "Change diagram")))
           .replace("<!--{{SUBTITLE}}-->", html.escape(graph.get("subtitle", "")))
           .replace("<!--{{NAV}}-->", nav)
           .replace("<!--{{SOURCE}}-->", src_html)
           .replace("/*{{ROOT}}*/", json.dumps(graph.get("root", "")))
           .replace("/*{{EDITOR}}*/", json.dumps(graph.get("editor", "system")))
           .replace("/*{{DATA}}*/", json.dumps(meta))
           .replace("<!--{{SVG}}-->", svg))
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    open(dst, "w").write(out)
    open(os.path.splitext(dst)[0] + ".d2", "w").write(d2_text)
    print("wrote %s (%d nodes, %d edges%s)"
          % (dst, len(graph["nodes"]), len(graph["edges"]),
             ", %d unbound" % len(missing) if missing else ""))


if __name__ == "__main__":
    main()
