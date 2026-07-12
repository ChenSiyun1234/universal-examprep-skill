# -*- coding: utf-8 -*-
"""v4-P3 — scripts/retrieve.py: BM25 index build/search, zh bigram tokenization, terms.json
cross-lingual expansion, abstain gate, and the old-workspace no-index degradation contract.
Stdlib only; synthetic corpus fixtures (no real course data)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)
import retrieve  # noqa: E402

PY = sys.executable


def run_cli(*args):
    return subprocess.run([PY, os.path.join(SCRIPTS, "retrieve.py")] + list(args),
                          capture_output=True, text=True, encoding="utf-8")


def make_ws(chunks, terms=None, write_index=True):
    ws = tempfile.mkdtemp(prefix="rtv_")
    for c in chunks:
        path = os.path.join(ws, c["file"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(c["text"])
    os.makedirs(os.path.join(ws, "references"), exist_ok=True)
    if write_index:
        idx = retrieve.build_index(chunks)
        with open(os.path.join(ws, "references", "retrieval_index.json"), "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False)
    if terms is not None:
        with open(os.path.join(ws, "references", "terms.json"), "w", encoding="utf-8") as f:
            json.dump(terms, f, ensure_ascii=False)
    return ws


CORPUS = [
    {"id": "ch01/s01", "file": "references/wiki/ch01/s01_intro.md", "chapter": "1",
     "title": "Word-RAM model",
     "text": "The model of computation in this class is called the Word-RAM. "
             "Memory is an array of w-bit words; operations cost constant time."},
    {"id": "ch02/s01", "file": "references/wiki/ch02/s01_sort.md", "chapter": "2",
     "title": "Sorting lower bounds",
     "text": "Comparison sorting requires Omega(n log n) comparisons in the worst case. "
             "Merge sort achieves this bound and is stable."},
    {"id": "ch03/s01", "file": "references/wiki/ch03/s01_bystander.md", "chapter": "3",
     "title": "Bystander effect",
     "text": "The bystander effect: the presence of others reduces helping. "
             "Darley and Latane ran the classic smoke-filled room experiment."},
]


class Tokenize(unittest.TestCase):
    def test_ascii_words_lowercased(self):
        self.assertEqual(retrieve.tokenize("Word-RAM Model 2024"), ["word-ram", "model", "2024"])

    def test_cjk_becomes_bigrams(self):
        self.assertEqual(retrieve.tokenize("旁观者效应"), ["旁观", "观者", "者效", "效应"])

    def test_single_cjk_char_is_unigram(self):
        self.assertEqual(retrieve.tokenize("树"), ["树"])

    def test_mixed_language_query(self):
        toks = retrieve.tokenize("什么是Word-RAM模型")
        self.assertIn("word-ram", toks)
        self.assertIn("什么", toks)
        self.assertIn("模型", toks)


class IndexBuild(unittest.TestCase):
    def test_index_shape_and_postings(self):
        idx = retrieve.build_index(CORPUS)
        self.assertEqual(idx["version"], retrieve.INDEX_VERSION)
        self.assertEqual(idx["n_docs"], 3)
        self.assertEqual(len(idx["docs"]), 3)
        self.assertIn("word-ram", idx["vocab"])       # posting exists for the distinctive term
        self.assertGreater(idx["avgdl"], 0)

    def test_missing_field_fails_loud(self):
        with self.assertRaises(SystemExit):
            retrieve.build_index([{"id": "x", "file": ""}])


class Search(unittest.TestCase):
    def test_relevant_chunk_ranks_first(self):
        ws = make_ws(CORPUS)
        try:
            hits, _ = retrieve.search(ws, retrieve.load_index(ws), "word-ram model of computation")
            self.assertTrue(hits)
            self.assertEqual(hits[0]["id"], "ch01/s01")
            self.assertGreater(hits[0]["score"], 0)
            self.assertIn("Word-RAM", hits[0]["text"])   # snippet comes from the chunk file
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_cross_lingual_terms_expansion(self):
        # zh query hits the EN bystander chunk only via terms.json
        terms = {"旁观者效应": ["bystander effect"]}
        ws = make_ws(CORPUS, terms=terms)
        try:
            hits, _ = retrieve.search(ws, retrieve.load_index(ws), "旁观者效应 是什么")
            self.assertTrue(hits, "terms.json 扩展后 zh 查询应命中 en 材料")
            self.assertEqual(hits[0]["id"], "ch03/s01")
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_zero_hit_returns_empty(self):
        ws = make_ws(CORPUS)
        try:
            hits, _ = retrieve.search(ws, retrieve.load_index(ws), "quantum chromodynamics")
            self.assertEqual(hits, [])
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_min_score_gates_low_hits(self):
        ws = make_ws(CORPUS)
        try:
            idx = retrieve.load_index(ws)
            hits, _ = retrieve.search(ws, idx, "word-ram", min_score=10 ** 6)
            self.assertEqual(hits, [], "高于任何真实分值的门限应清空命中（弃答）")
        finally:
            shutil.rmtree(ws, ignore_errors=True)


class CliContract(unittest.TestCase):
    def test_hits_exit_0_and_json_shape(self):
        ws = make_ws(CORPUS)
        try:
            r = run_cli("--workspace", ws, "--query", "merge sort lower bound", "--json")
            self.assertEqual(r.returncode, 0, r.stderr)
            payload = json.loads(r.stdout)
            self.assertFalse(payload["abstain"])
            self.assertEqual(payload["hits"][0]["id"], "ch02/s01")
            for k in ("id", "file", "score", "text"):
                self.assertIn(k, payload["hits"][0])   # spike Chunk contract superset
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_abstain_exit_4(self):
        ws = make_ws(CORPUS)
        try:
            r = run_cli("--workspace", ws, "--query", "totally unrelated nonsense zzz", "--json")
            self.assertEqual(r.returncode, 4, "零命中必须走弃答退出码")
            self.assertTrue(json.loads(r.stdout)["abstain"])
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_no_index_degrades_exit_3(self):
        ws = make_ws(CORPUS, write_index=False)
        try:
            r = run_cli("--workspace", ws, "--query", "anything")
            self.assertEqual(r.returncode, 3, "无索引 = 老工作区，须走降级码而非报错")
            self.assertIn("no_index", r.stderr)
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_wrong_index_version_fails_loud(self):
        ws = make_ws(CORPUS)
        try:
            p = os.path.join(ws, "references", "retrieval_index.json")
            with open(p, "r", encoding="utf-8") as f:
                idx = json.load(f)
            idx["version"] = 999
            with open(p, "w", encoding="utf-8") as f:
                json.dump(idx, f)
            r = run_cli("--workspace", ws, "--query", "word-ram")
            self.assertEqual(r.returncode, 2)
            self.assertIn("version", r.stderr)
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_bad_usage(self):
        ws = make_ws(CORPUS)
        try:
            self.assertEqual(run_cli("--workspace", ws, "--query", "x", "-k", "0").returncode, 2)
            self.assertEqual(run_cli("--workspace", ws, "--query", "x",
                                     "--min-score", "-1").returncode, 2)
        finally:
            shutil.rmtree(ws, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
