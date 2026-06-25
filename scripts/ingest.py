#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import json
import argparse

def get_template_path(template_name):
    # 脚本所在目录: .agents/skills/universal-exam-cram-coach/scripts/
    # 模板所在目录: .agents/skills/universal-exam-cram-coach/templates/
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(script_dir, '..', 'templates', template_name)
    if os.path.exists(template_path):
        return template_path
    return None

def main():
    parser = argparse.ArgumentParser(description="一键解析并生成备考 LLM Wiki 目录结构与进度文件")
    parser.add_argument("--input", "-i", type=str, default="raw_input.json", help="输入的结构化大纲 JSON 文件路径")
    parser.add_argument("--output-dir", "-o", type=str, default=".", help="输出的目标工作区路径 (默认为当前目录)")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[-] 错误: 输入文件 '{args.input}' 不存在。")
        print("请提供正确的 JSON 数据文件。格式示例:")
        print(json.dumps({
            "course_name": "科目名称",
            "phases": [
                {
                    "phase_num": 1,
                    "phase_name": "基础概念篇",
                    "wiki_filename": "ch1_concepts.md",
                    "wiki_content": "# 阶段一：基础概念篇\n\n内容..."
                }
            ],
            "quiz_bank": []
        }, indent=2, ensure_ascii=False))
        sys.exit(1)

    print(f"[+] 正在读取输入数据: {args.input} ...")
    with open(args.input, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except Exception as e:
            print(f"[-] 错误: JSON 解析失败. {e}")
            sys.exit(1)

    course_name = data.get("course_name", "未命名科目")
    phases = data.get("phases", [])
    quiz_bank = data.get("quiz_bank", [])

    print(f"[+] 识别到科目: {course_name}")
    print(f"[+] 阶段数量: {len(phases)} 个")
    print(f"[+] 题目数量: {len(quiz_bank)} 道")

    # 创建目标目录
    output_dir = os.path.abspath(args.output_dir)
    wiki_dir = os.path.join(output_dir, "references", "wiki")
    os.makedirs(wiki_dir, exist_ok=True)
    print(f"[+] 创建 Wiki 目录: {wiki_dir}")

    # 1. 写入各阶段 Wiki 文件
    for phase in phases:
        p_num = phase.get("phase_num")
        p_name = phase.get("phase_name", f"第{p_num}阶段")
        filename = phase.get("wiki_filename", f"ch{p_num}_notes.md")
        content = phase.get("wiki_content", f"# {p_name}\n\n暂无内容。")

        wiki_file_path = os.path.join(wiki_dir, filename)
        with open(wiki_file_path, 'w', encoding='utf-8') as wf:
            wf.write(content)
        print(f"[+] 已写入 Wiki 文件: references/wiki/{filename}")

    # 2. 写入题库 JSON
    quiz_file_path = os.path.join(output_dir, "references", "quiz_bank.json")
    with open(quiz_file_path, 'w', encoding='utf-8') as qf:
        json.dump(quiz_bank, qf, indent=2, ensure_ascii=False)
    print(f"[+] 已写入题库文件: references/quiz_bank.json")

    # 3. 生成 study_plan.md
    plan_template_path = get_template_path("study_plan_template.md")
    plan_out_path = os.path.join(output_dir, "study_plan.md")
    if plan_template_path:
        with open(plan_template_path, 'r', encoding='utf-8') as tf:
            plan_content = tf.read()
        # 替换科目名称
        plan_content = plan_content.replace("《科目名称》", f"《{course_name}》")
        
        # 尝试动态生成阶段表格内容（如果 JSON 中的阶段数不等于默认的 6 个）
        if len(phases) > 0:
            table_lines = [
                "| 阶段 | 核心任务 | 关联 Wiki 章节文件 | 状态 |",
                "| :--- | :--- | :--- | :--- |"
            ]
            for p in phases:
                p_num = p.get("phase_num")
                p_name = p.get("phase_name")
                filename = p.get("wiki_filename", f"ch{p_num}_notes.md")
                table_lines.append(f"| **阶段 {p_num}** | {p_name} | `references/wiki/{filename}` | 未开始 |")
            # 追加模拟测验和错题阶段
            table_lines.append(f"| **模拟测试** | 综合真题自测 | `references/quiz_bank.json` | 未开始 |")
            table_lines.append(f"| **易错扫雷** | 错题本重温与考前小抄 | `study_progress.md` 错题本 | 未开始 |")
            
            # 简单替换表格
            if "## 📅 阶段复习进度表" in plan_content:
                parts = plan_content.split("## 📅 阶段复习进度表")
                plan_content = parts[0] + "## 📅 阶段复习进度表\n\n" + "\n".join(table_lines) + "\n"

        with open(plan_out_path, 'w', encoding='utf-8') as pf:
            pf.write(plan_content)
        print("[+] 已生成: study_plan.md")
    else:
        print("[-] 警告: 未找到 study_plan_template.md，跳过生成。")

    # 4. 生成 study_progress.md
    progress_template_path = get_template_path("study_progress_template.md")
    progress_out_path = os.path.join(output_dir, "study_progress.md")
    if progress_template_path:
        with open(progress_template_path, 'r', encoding='utf-8') as tf:
            prog_content = tf.read()
        prog_content = prog_content.replace("《科目名称》", f"《{course_name}》")
        
        # 如果阶段数不同，动态调整打卡状态列表
        if len(phases) > 0:
            list_lines = []
            for p in phases:
                p_num = p.get("phase_num")
                p_name = p.get("phase_name")
                filename = p.get("wiki_filename", f"ch{p_num}_notes.md")
                list_lines.append(f"- [ ] **阶段 {p_num}**：{p_name} (关联 `references/wiki/{filename}`)")
            list_lines.append(f"- [ ] **模拟测试**：综合真题自测 (关联 `references/quiz_bank.json`)")
            list_lines.append(f"- [ ] **易错扫雷**：错题自测 (关联 错题自测)")
            
            if "## 📊 知识点打卡状态" in prog_content:
                parts = prog_content.split("## 📊 知识点打卡状态")
                subparts = parts[1].split("## ❌ 错题档案记录")
                prog_content = parts[0] + "## 📊 知识点打卡状态\n" + "\n".join(list_lines) + "\n\n## ❌ 错题档案记录" + subparts[1]

        with open(progress_out_path, 'w', encoding='utf-8') as prf:
            prf.write(prog_content)
        print("[+] 已生成: study_progress.md")
    else:
        print("[-] 警告: 未找到 study_progress_template.md，跳过生成。")

    print(f"\n[+] 恭喜! 《{course_name}》的 LLM Wiki 备考环境初始化成功！")
    print("你可以直接开始复习了。")

if __name__ == "__main__":
    main()
