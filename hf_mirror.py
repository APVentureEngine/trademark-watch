#!/usr/bin/env python3
"""Mirror the live Gazette word-mark window to Hugging Face Datasets.

Second autonomous discovery channel for TM Watch (c73). HF dataset search +
Google index dataset cards; the viewer renders our CSV for free. Reads ONLY
marks.jsonl (the same rows the public site index is built from), so every
surface says the same thing. Deterministic: card stats come from the data
(newest pub_date, row count), never now().

Usage (from product/, after refresh.sh's index build):
  python3 hf_mirror.py                 # stage + upload (needs HF_TOKEN)
  HF_STAGE_ONLY=1 python3 hf_mirror.py # stage only, no network
Non-fatal by design in refresh.sh: a mirror hiccup must never block the site.
"""
import csv
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MARKS = os.path.join(HERE, "marks.jsonl")
STAGE = os.environ.get("HF_STAGE_DIR", os.path.join(HERE, "hf_staging"))
DATASET_NAME = "uspto-trademark-gazette-word-marks"  # renamed c91: HF search matches repo-id tokens; "trademark" had to be in the id (old id 307-redirects)
COLS = ["serial", "mark", "event", "pub_date", "filing_date", "classes", "owner", "status"]

CARD = """---
pretty_name: USPTO Trademark Official Gazette — word marks (rolling 120 days, weekly refresh)
license: cc0-1.0
language:
  - en
task_categories:
  - text-classification
  - text-retrieval
tags:
  - trademarks
  - uspto
  - trademark-search
  - public-records
  - government-data
  - weekly-updated
  - intellectual-property
  - official-gazette
  - brand-names
  - united-states
  - trademark
  - trademark-monitoring
  - brand-protection
  - legal
  - nlp
  - entity-matching
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/gazette_word_marks.csv
---

# USPTO Trademark Official Gazette — word marks, rolling window, refreshed weekly

Every **word mark published for opposition or registered** in the USPTO
Trademark Official Gazette over the last ~120 days, parsed from the weekly
ST.96 XML issues and kept current by an automated pipeline. **{n_rows:,} rows**
across **{n_issues} weekly issues** ({first_issue} → {last_issue}). Newest issue:
**{last_issue}**. Design-only marks are excluded (no text to match on).

This is a live mirror of the index behind
[TM Watch](https://apventureengine.github.io/trademark-watch/) — a free,
in-browser similarity check (edit distance + phonetic + variant forms,
benchmarked on real §2(d) pairs; matcher and benchmark are open source at
[github.com/APVentureEngine/trademark-watch](https://github.com/APVentureEngine/trademark-watch)).

## Quickstart

```python
from datasets import load_dataset
ds = load_dataset("APProjects/uspto-trademark-gazette-word-marks", split="train")
print(ds[0])
```

```python
import pandas as pd
df = pd.read_csv("https://huggingface.co/datasets/APProjects/"
                 "uspto-trademark-gazette-word-marks/resolve/main/data/gazette_word_marks.csv")
df[df["event"] == "published"].head()
```

## Schema

| column | meaning |
|---|---|
| `serial` | USPTO application serial number (link: `https://tsdr.uspto.gov/#caseNumber=<serial>&caseType=SERIAL_NO&searchType=statusSearch`) |
| `mark` | the word mark as published (uppercase, as in the Gazette) |
| `event` | `published` (published for opposition) or `registered` |
| `pub_date` | Gazette issue date (Tuesdays) |
| `filing_date` | application filing date |
| `classes` | space-separated Nice international classes |
| `owner` | applicant / registrant name as published |
| `status` | USPTO status code at publication |

## Permanent per-issue copies

This mirror is a rolling ~120-day window. If you need a **citable, immutable**
copy of a single Gazette issue, the same records are published as one CSV per
issue (never rewritten) at
[apventureengine.github.io/trademark-watch/data/](https://apventureengine.github.io/trademark-watch/data/)
— public domain (CC0), no login, with a `manifest.json` listing every issue.

## Why a rolling window

A mark published for opposition can be opposed (or an extension of time
requested) for **30 days from its Gazette date** — the recent window is the
part that is actionable. Older issues fall out as new ones arrive; a static
copy of this file is stale within a week. The full historical bulk data was
formerly on bulkdata.uspto.gov (decommissioned 2026-06) and now requires an
authenticated USPTO Open Data Portal key; the Gazette issues themselves are
public.

## Not legal advice

Similarity flags are for human review; nothing here is an opinion on
likelihood of confusion. Source data is a US government work (public domain).
"""


def build_stage():
    rows, issues = [], set()
    with open(MARKS) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            issues.add(r.get("pub_date") or "")
            rows.append([r.get("serial", ""), r.get("mark", ""), r.get("event", ""),
                         r.get("pub_date", ""), r.get("filing_date", ""),
                         " ".join(str(c) for c in r.get("classes", [])),
                         r.get("owner", ""), r.get("status", "")])
    rows.sort(key=lambda x: (x[3], x[0]))
    issues.discard("")
    if os.path.isdir(STAGE):
        shutil.rmtree(STAGE)
    os.makedirs(os.path.join(STAGE, "data"))
    with open(os.path.join(STAGE, "data", "gazette_word_marks.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        w.writerows(rows)
    card = CARD.format(n_rows=len(rows), n_issues=len(issues),
                       first_issue=min(issues), last_issue=max(issues))
    with open(os.path.join(STAGE, "README.md"), "w") as f:
        f.write(card)
    print("hf_mirror: staged %d rows, %d issues (%s..%s) -> %s"
          % (len(rows), len(issues), min(issues), max(issues), STAGE))
    return len(rows)


def upload():
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("hf_mirror: HF_TOKEN not set — staged only, nothing uploaded.")
        return 0
    from huggingface_hub import HfApi
    api = HfApi(token=token)
    user = api.whoami()["name"]
    repo_id = "%s/%s" % (user, DATASET_NAME)
    api.create_repo(repo_id, repo_type="dataset", exist_ok=True)
    api.upload_folder(folder_path=STAGE, repo_id=repo_id, repo_type="dataset",
                      commit_message="weekly Gazette refresh mirror")
    print("hf_mirror: uploaded -> https://huggingface.co/datasets/%s" % repo_id)
    return 0


if __name__ == "__main__":
    if not os.path.exists(MARKS):
        print("hf_mirror: no marks.jsonl — nothing to mirror")
        sys.exit(0)
    build_stage()
    if os.environ.get("HF_STAGE_ONLY"):
        sys.exit(0)
    sys.exit(upload())
