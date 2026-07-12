# -*- coding: utf-8 -*-
"""v4-P3 — ingest v2 wiring: a fresh workspace gets retrieval_index.json + wiki_meta.json
(+ terms.json passthrough), wiki chapter files stay byte-for-byte verbatim (v3 contract),
and the retrieve CLI routes a query to the right chapter of the freshly built workspace."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
PY = sys.executable

RAW = {
    "course_name": "数据结构",
    "phases": [
        {"phase_num": 1, "phase_name": "线性表", "wiki_filename": "ch1_linear.md",
         "wiki_content": "# 线性表\n\n## 链表\n链表由节点组成，访问代价 O(n)。头指针 head 指向首节点。\n\n"
                         "## 顺序表\n顺序表支持随机访问，插入需要搬移元素。" + " 细节补充。" * 40},
        {"phase_num": 2, "phase_name": "排序", "wiki_filename": "ch2_sort.md",
         "wiki_content": "# 排序\n\n## 归并排序\nMerge sort 是稳定排序，时间复杂度 O(n log n)。\n\n"
                         "## 快速排序\n快排平均 O(n log n)，最坏 O(n^2)，不稳定。" + " 细节补充。" * 40},
    ],
    "quiz_bank": [
        {"id": "q1", "phase": 1, "type": "choice", "question": "链表访问代价？",
         "options": ["O(1)", "O(n)"], "answer": "O(n)", "source": "teacher_provided"},
    ],
    "terms": {"归并排序": ["merge sort"], "链表": ["linked list"]},
}


def build_ws():
    tmp = tempfile.mkdtemp(prefix="ing2_")
    raw_path = os.path.join(tmp, "raw_input.json")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(RAW, f, ensure_ascii=False)
    ws = os.path.join(tmp, "ws")
    r = subprocess.run([PY, os.path.join(SCRIPTS, "ingest.py"), "--input", raw_path,
                        "--output-dir", ws], capture_output=True, text=True, encoding="utf-8")
    return tmp, ws, r


class IngestIndex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp, cls.ws, cls.r = build_ws()
        if cls.r.returncode != 0:
            raise AssertionError("ingest failed:\n" + cls.r.stdout + cls.r.stderr)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_wiki_files_stay_verbatim(self):
        for p in RAW["phases"]:
            with open(os.path.join(self.ws, "references", "wiki", p["wiki_filename"]),
                      encoding="utf-8") as f:
                self.assertEqual(f.read(), p["wiki_content"],
                                 "v3 契约：章文件逐字写盘，索引化不得改动它")

    def test_retrieval_index_built(self):
        path = os.path.join(self.ws, "references", "retrieval_index.json")
        self.assertTrue(os.path.isfile(path), "ingest v2 必须产出检索索引")
        with open(path, encoding="utf-8") as f:
            idx = json.load(f)
        self.assertGreaterEqual(idx["n_docs"], 4, "两章各至少两小节")
        ids = {d["id"] for d in idx["docs"]}
        self.assertTrue(any(i.startswith("ch01#") for i in ids))
        self.assertTrue(any(i.startswith("ch02#") for i in ids))

    def test_wiki_meta_hashes(self):
        with open(os.path.join(self.ws, "references", "wiki_meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        for p in RAW["phases"]:
            m = meta[p["wiki_filename"]]
            self.assertEqual(m["chapter"], p["phase_num"])
            self.assertGreater(m["n_chunks"], 0)
            self.assertEqual(len(m["sha256"]), 64)

    def test_terms_passthrough(self):
        with open(os.path.join(self.ws, "references", "terms.json"), encoding="utf-8") as f:
            terms = json.load(f)
        self.assertEqual(terms["链表"], ["linked list"])

    def test_retrieve_routes_to_right_chapter(self):
        r = subprocess.run([PY, os.path.join(SCRIPTS, "retrieve.py"), "--workspace", self.ws,
                            "--query", "merge sort 稳定吗", "--json"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        hits = json.loads(r.stdout)["hits"]
        self.assertEqual(hits[0]["chapter"], "2", "terms/内容应把归并排序问题路由到第 2 章")

    def test_retrieve_abstains_on_oos(self):
        r = subprocess.run([PY, os.path.join(SCRIPTS, "retrieve.py"), "--workspace", self.ws,
                            "--query", "quantum entanglement paradox", "--json"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 4, "材料外问题必须走弃答退出码")


class NoTermsNoFile(unittest.TestCase):
    def test_absent_terms_writes_nothing(self):
        raw = {k: v for k, v in RAW.items() if k != "terms"}
        tmp = tempfile.mkdtemp(prefix="ing2_")
        try:
            rp = os.path.join(tmp, "raw_input.json")
            with open(rp, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False)
            ws = os.path.join(tmp, "ws")
            r = subprocess.run([PY, os.path.join(SCRIPTS, "ingest.py"), "--input", rp,
                                "--output-dir", ws], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertFalse(os.path.exists(os.path.join(ws, "references", "terms.json")))
            self.assertTrue(os.path.exists(os.path.join(ws, "references", "retrieval_index.json")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
