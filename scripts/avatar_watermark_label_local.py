"""B3-L6 Part A - build a blinded, network-free local labeling UI for human raters.

LOCAL ONLY. Writes a single self-contained HTML file into the restricted local
directory. The page:

  * shows ONLY the image and the PR #114 taxonomy -- never a detector box, a
    detector score, Florence OCR/OD output, watermarkQaAction, an H1/H2/H3
    action, reviewReasons/rejectReasons, or a preview result;
  * identifies every image by an opaque evaluation ID; the real filename never
    appears (images are inlined as data URIs, so the page carries no path);
  * makes no network request of any kind (no remote script, style, font or
    image; a CSP meta tag blocks it even if one were added later);
  * exports labels with the allowed fields only.

Raters work independently: build one page per rater with --rater, and a rater's
page never contains another rater's labels.

  python scripts/avatar_watermark_label_local.py --private-dir <dir> --rater A --out <dir>
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_florence_ceiling as bench  # noqa: E402

UI_VERSION = "avatar_watermark_label_local_v1"
LABEL_SCHEMA_VERSION = "avatar_watermark_label_schema_v2"

PRIMARY_LABELS = (
    "NO_VISIBLE_RELEVANT_TEXT_OR_MARK",
    "GARMENT_TEXT",
    "BACKGROUND_SIGNAGE",
    "BRAND_TEXT_OR_MARK",
    "OVERLAY_TEXT",
    "OVERLAY_WATERMARK",
    "GRAPHICAL_LOGO",
    "GENERATIVE_TEXT_ARTIFACT",
    "UNCERTAIN",
)
VISIBLE_GRAPHICAL_MARK = ("yes", "no", "uncertain")
MARK_INTEGRATION = ("scene_native", "overlay_like", "uncertain", "not_applicable")
MARK_TYPE = (
    "brand_or_object_mark",
    "graphical_logo",
    "watermark",
    "other_mark",
    "none",
    "uncertain",
)
LABEL_CONFIDENCE = ("high", "medium", "low")

# Never rendered into the page. Asserted by the tests.
FORBIDDEN_IN_UI = (
    "owlv2",
    "grounding-dino",
    "florence",
    "watermarkQaAction",
    "previewAllowed",
    "rejectReasons",
    "reviewReasons",
    "shadowWatermarkAction",
    "score",
    "detection",
)

_CSS = """
body{font:14px/1.5 system-ui,sans-serif;margin:0;background:#111;color:#eee}
header{position:sticky;top:0;background:#000;padding:10px 16px;border-bottom:1px solid #333;z-index:2}
main{padding:16px;max-width:1100px;margin:0 auto}
.item{border:1px solid #333;border-radius:8px;padding:12px;margin-bottom:24px;background:#181818}
.item img{max-width:100%;max-height:70vh;display:block;margin:0 auto 12px;background:#000}
.eid{font-family:ui-monospace,monospace;color:#9cf}
fieldset{border:1px solid #333;border-radius:6px;margin:8px 0}
legend{color:#aaa;padding:0 6px}
label{display:inline-block;margin:2px 10px 2px 0;white-space:nowrap}
button{font:inherit;padding:8px 14px;border-radius:6px;border:1px solid #555;background:#222;color:#eee;cursor:pointer}
#status{color:#9f9;margin-left:10px}
textarea{width:100%;height:180px;background:#000;color:#9f9;font-family:ui-monospace,monospace}
.warn{color:#fc9}
"""

_JS = """
const RATER = %(rater)s, ITEMS = %(ids)s, SCHEMA = %(schema)s, UI = %(ui)s, STATE = %(state)s;
const KEY = 'b3l6-labels-' + STATE + '-' + RATER;
function load(){ try { return JSON.parse(localStorage.getItem(KEY) || '{}'); } catch(e) { return {}; } }
function save(d){ try { localStorage.setItem(KEY, JSON.stringify(d)); } catch(e) {} }
function collect(){
  const out = {};
  for (const id of ITEMS){
    const row = {};
    for (const field of ['primaryLabel','visibleGraphicalMark','markIntegration','markType','labelConfidence']){
      const el = document.querySelector(`input[name="${field}:${id}"]:checked`);
      if (el) row[field] = el.value;
    }
    row.allVisibleClasses = Array.from(document.querySelectorAll(`input[name="allVisible:${id}"]:checked`)).map(e => e.value);
    if (row.primaryLabel) out[id] = row;
  }
  return out;
}
function refresh(){
  const done = Object.keys(collect()).length;
  document.getElementById('status').textContent = `${done} / ${ITEMS.length} labeled`;
  save(collect());
}
function restore(){
  const data = load();
  for (const [id, row] of Object.entries(data)){
    for (const [field, value] of Object.entries(row)){
      if (field === 'allVisibleClasses'){
        for (const v of value){
          const box = document.querySelector(`input[name="allVisible:${id}"][value="${v}"]`);
          if (box) box.checked = true;
        }
      } else {
        const el = document.querySelector(`input[name="${field}:${id}"][value="${value}"]`);
        if (el) el.checked = true;
      }
    }
  }
  refresh();
}
function exportLabels(){
  const rows = collect();
  const payload = {
    uiVersion: UI, labelSchema: SCHEMA, raterId: RATER,
    adjudicationState: STATE,
    labels: ITEMS.map(id => Object.assign({evaluationId: id}, rows[id] || {})).filter(r => r.primaryLabel)
  };
  const text = JSON.stringify(payload, null, 2);
  document.getElementById('export').value = text;
  try {
    const blob = new Blob([text], {type: 'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = STATE === 'first_pass' ? `b3l6-labels-rater-${RATER}.json` : `b3l6-adjudication-rater-${RATER}.json`;
    a.click();
  } catch(e) {}
}
document.addEventListener('change', refresh);
window.addEventListener('DOMContentLoaded', restore);
"""


def _data_uri(path: Path) -> str:
    from PIL import Image

    with Image.open(path) as handle:
        image = handle.convert("RGB")
    if max(image.size) > 1400:
        scale = 1400 / max(image.size)
        image = image.resize((round(image.width * scale), round(image.height * scale),), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _radios(field: str, eid: str, values) -> str:
    return "".join(
        f'<label><input type="radio" name="{field}:{eid}" value="{html.escape(v)}"> {html.escape(v)}</label>'
        for v in values
    )


def build_html(entries, rater: str, *, adjudication_state: str = "first_pass") -> str:
    """One page per rater. A third adjudicator gets the same blind page over the
    unresolved subset only: it never carries either first-pass vote, and its
    export is stamped third_adjudication so the ingest can tell it apart."""

    ids = [e["opaqueId"] for e in entries]
    items = []
    for entry in entries:
        eid = html.escape(entry["opaqueId"])
        checks = "".join(
            f'<label><input type="checkbox" name="allVisible:{eid}" value="{html.escape(v)}"> {html.escape(v)}</label>'
            for v in PRIMARY_LABELS
            if v != "UNCERTAIN"
        )
        items.append(
            f"""<section class="item">
<h2 class="eid">{eid}</h2>
<img src="{entry['dataUri']}" alt="image {eid}">
<fieldset><legend>primary label (one)</legend>{_radios('primaryLabel', eid, PRIMARY_LABELS)}</fieldset>
<fieldset><legend>all visible classes (any)</legend>{checks}</fieldset>
<fieldset><legend>visibleGraphicalMark</legend>{_radios('visibleGraphicalMark', eid, VISIBLE_GRAPHICAL_MARK)}</fieldset>
<fieldset><legend>markIntegration</legend>{_radios('markIntegration', eid, MARK_INTEGRATION)}</fieldset>
<fieldset><legend>markType</legend>{_radios('markType', eid, MARK_TYPE)}</fieldset>
<fieldset><legend>confidence</legend>{_radios('labelConfidence', eid, LABEL_CONFIDENCE)}</fieldset>
</section>"""
        )
    script = _JS % {
        "rater": json.dumps(rater),
        "ids": json.dumps(ids),
        "schema": json.dumps(LABEL_SCHEMA_VERSION),
        "ui": json.dumps(UI_VERSION),
        "state": json.dumps(adjudication_state),
    }
    role = "third adjudicator" if adjudication_state == "third_adjudication" else "rater"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>B3-L6 labeling - {role} {html.escape(rater)}</title>
<style>{_CSS}</style></head>
<body>
<header><strong>B3-L6 human labeling</strong> - {role} {html.escape(rater)}
<span id="status"></span>
<button type="button" onclick="exportLabels()">Export labels</button>
<div class="warn">Label from the image only. Do not discuss items with the other raters, and do not ask what they answered.</div>
</header>
<main>
{''.join(items)}
<h3>Exported JSON (save this file)</h3>
<textarea id="export" readonly></textarea>
</main>
<script>{script}</script>
</body></html>"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--rater", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--domain", default=bench.DOMAIN_AVATAR)
    # Third adjudication: a blind page over the unresolved subset only. The
    # ids come from the ingest report; the page never sees either prior vote.
    parser.add_argument("--adjudication-ids", type=Path, help="JSON with 'unresolvedIds' (an ingest report)")
    args = parser.parse_args(argv)
    manifest = json.loads((args.private_dir / "restricted_manifest.json").read_text(encoding="utf-8"))
    entries = [e for e in manifest["entries"] if e["domain"] == args.domain]
    expected = bench.EXPECTED_COUNTS.get(args.domain)
    if expected and len(entries) != expected:
        tag = "SOURCE" if args.domain == bench.DOMAIN_SOURCE else "AVATAR"
        raise SystemExit(f"BLOCKED_G004_{tag}_SET_COUNT_{len(entries)}")
    state = "first_pass"
    if args.adjudication_ids:
        wanted = set(json.loads(args.adjudication_ids.read_text(encoding="utf-8"))["unresolvedIds"])
        entries = [e for e in entries if e["opaqueId"] in wanted]
        if len(entries) != len(wanted):
            raise SystemExit("ADJUDICATION_IDS_NOT_IN_CORPUS")
        state = "third_adjudication"
    prepared = [{"opaqueId": e["opaqueId"], "dataUri": _data_uri(Path(e["path"]))} for e in entries]
    args.out.mkdir(parents=True, exist_ok=True)
    prefix = "adjudication" if state == "third_adjudication" else "label"
    target = args.out / f"{prefix}-rater-{args.rater}.html"
    target.write_text(build_html(prepared, args.rater, adjudication_state=state), encoding="utf-8")
    worksheet = args.out / f"worksheet-{prefix}-rater-{args.rater}.json"
    worksheet.write_text(
        json.dumps(
            {
                "uiVersion": UI_VERSION,
                "labelSchema": LABEL_SCHEMA_VERSION,
                "raterId": args.rater,
                "domain": args.domain,
                "primaryLabels": list(PRIMARY_LABELS),
                "visibleGraphicalMark": list(VISIBLE_GRAPHICAL_MARK),
                "markIntegration": list(MARK_INTEGRATION),
                "markType": list(MARK_TYPE),
                "items": [{"evaluationId": e["opaqueId"]} for e in prepared],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"html": str(target), "items": len(prepared), "worksheet": str(worksheet)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
