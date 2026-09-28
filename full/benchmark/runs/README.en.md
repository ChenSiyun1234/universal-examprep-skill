# Run Ledger (B7)

English · [中文](README.md)

Every **real** run (T5c live smoke, rejudge export, and in the future matrix generation/long sessions/judge calibration) appends one line to
`benchmark/runs/ledger.jsonl`: run_id / kind / model / prompt_hash / workspace_hash /
transcript_path / summary_path / cost·tokens / exit_code / notes / created_at. "Which model, which
prompt, which workspace, how much it cost, where the outputs are" can all be looked up in one place.

```bash
python benchmark/runs/ledger.py record --kind live_smoke --model claude-x --transcript /tmp/t.jsonl --exit-code 0
python benchmark/runs/ledger.py show --last 5
python benchmark/runs/ledger.py verify
```

Honest limits:
- `ledger.jsonl` is a **local artifact** (gitignored; it may contain private course paths). Only this module, the schema and self-authored samples are committed;
- The hashes are for **reproducible bookkeeping** (whether the prompt/workspace changed), not security signatures; cost/tokens are reported by the caller, and the ledger does not measure them itself;
- **Bookkeeping never affects a run**: the integrations (run_live_smoke / rejudge --scores-out) downgrade a bookkeeping failure to a notice.
