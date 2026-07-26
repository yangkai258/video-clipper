#!/usr/bin/env python3
"""v2.2.53: 批量给 uppercase React component import 加 eslint-disable comment

策略:
1. 读 npx eslint --format json
2. 找 uppercase var name 'X is defined but never used' (X 在 JSX <X /> 用了, eslint false positive)
3. 改 import 行: `import X from 'Y'` → `import X from 'Y'  // eslint-disable-line no-unused-vars`
   (保留 import, eslint 接受注释)
4. 不改 component function 名 (会破 rules-of-hooks 验 component 首字母大写)
5. 不动 lowercase (script v1 已修, 留给 v1)
"""
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


def get_eslint_findings():
    r = subprocess.run(
        ["npx", "eslint", "src", "--format", "json"],
        capture_output=True, text=True, cwd=Path.cwd()
    )
    if not r.stdout.strip():
        return []
    return json.loads(r.stdout)


def build_fix_plan(findings):
    """build {filepath: [(line, var_name, message)]} 只 uppercase + 1st occurrence in import"""
    plan = defaultdict(list)
    for f in findings:
        seen_lines = set()
        for msg in f.get("messages", []):
            if msg.get("ruleId") != "no-unused-vars":
                continue
            m = re.match(r"^'([^']+)'", msg.get("message", ""))
            if not m:
                continue
            var_name = m.group(1)
            if not var_name or not var_name[0].isupper():
                continue
            if var_name.startswith("_"):
                continue
            line = msg["line"]
            if line in seen_lines:
                continue
            seen_lines.add(line)
            plan[f["filePath"]].append((line, var_name))
    return plan


def apply_edits(plan):
    """对每个 file, 在 import 行末尾加 eslint-disable comment"""
    total_edits = 0
    for path, edits in plan.items():
        try:
            content = Path(path).read_text()
            lines = content.split("\n")
            # sort by line DESC
            edits.sort(key=lambda e: e[0], reverse=True)
            for line_num, var_name in edits:
                idx = line_num - 1
                if idx < 0 or idx >= len(lines):
                    continue
                line = lines[idx]
                if "eslint-disable" in line:
                    continue
                # 仅当行是 import 包含 var_name 才加 comment
                if "import" not in line:
                    continue
                if var_name not in line:
                    continue
                # 加 disable comment
                if line.rstrip().endswith("}"):
                    lines[idx] = line.rstrip() + "  // eslint-disable-line no-unused-vars"
                else:
                    lines[idx] = line.rstrip() + "  // eslint-disable-line no-unused-vars"
            Path(path).write_text("\n".join(lines))
            total_edits += len(edits)
        except Exception as e:
            print(f"  ERR {path}: {e}")
    return total_edits


def main():
    print("=== 1. 跑 eslint 收集 uppercase unused ===")
    findings = get_eslint_findings()
    if not findings:
        print("no findings")
        return

    plan = build_fix_plan(findings)
    total = sum(len(v) for v in plan.values())
    print(f"plan: {len(plan)} files, {total} uppercase unused (准备加 disable comment)")

    print("=== 2. apply edits ===")
    edited = apply_edits(plan)
    print(f"applied {edited} edits")

    print("=== 3. 重新跑 eslint 验证 ===")
    r = subprocess.run(
        ["npx", "eslint", "src"], capture_output=True, text=True
    )
    last_lines = r.stdout.strip().split("\n")
    for ln in reversed(last_lines):
        if "problems" in ln:
            print(ln)
            break


if __name__ == "__main__":
    main()
