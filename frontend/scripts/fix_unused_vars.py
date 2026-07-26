#!/usr/bin/env python3
"""v2.2.49: 批量修 eslint 128 个 no-unused-vars warning

策略:
1. unused import (import { X } from 'Y' X 没在 file 用) → 整行 import 删
2. unused let/const (let X = ... X 没在 file 用) → 改 `let _X = ...` (eslint varsIgnorePattern='^_')
3. unused var (let/const/var 但 is 显式 _) → 加 _ prefix
4. unused function param (e) catch → 改 _e (已配 caughtErrorsIgnorePattern)
5. 跳过 exhaustive-deps (8 个, 跟 deps 逻辑相关, 手修)
6. 跳过已有 _ prefix 的

读 eslint --format json 输出, 按 source 位置精准改.
"""
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


def get_eslint_findings():
    """跑 eslint --format json, 返 list[{filePath, line, column, ruleId, message, fix}]"""
    r = subprocess.run(
        ["npx", "eslint", "src", "--format", "json"],
        capture_output=True, text=True, cwd=Path.cwd()
    )
    if not r.stdout.strip():
        return []
    return json.loads(r.stdout)


def is_destructured_import_finding(ruleId, message):
    """unused import 行 / 列定位"""
    return "defined but never used" in message or "assigned a value but never used" in message


def build_fix_plan(findings):
    """build {filepath: [edit_ops]} """
    plan = defaultdict(list)
    for f in findings:
        for msg in f.get("messages", []):
            if msg.get("ruleId") != "no-unused-vars":
                continue
            if not is_destructured_import_finding("no-unused-vars", msg.get("message", "")):
                continue
            plan[f["filePath"]].append({
                "line": msg["line"],
                "column": msg["column"],
                "message": msg["message"],
                "endColumn": msg.get("endColumn", msg["column"] + 30),
            })
    return plan


def extract_var_name(message):
    """从 message 提 var name: 'X is defined but never used...' → X"""
    m = re.match(r"^'([^']+)'", message)
    if m:
        return m.group(1)
    return None


def read_file(path):
    return Path(path).read_text()


def write_file(path, content):
    Path(path).write_text(content)


def apply_edits(path, edits):
    """apply edits to file in reverse order (preserves line numbers)"""
    content = read_file(path)
    lines = content.split("\n")

    # sort by line DESC, col DESC
    edits.sort(key=lambda e: (e["line"], e["column"]), reverse=True)

    for ed in edits:
        line_idx = ed["line"] - 1
        if line_idx < 0 or line_idx >= len(lines):
            continue
        line = lines[line_idx]
        col_start = ed["column"] - 1
        col_end = ed["endColumn"] - 1
        if col_start < 0 or col_end > len(line):
            continue

        var_name = extract_var_name(ed["message"])
        if not var_name:
            continue

        # skip already-prefixed
        if var_name.startswith("_"):
            continue

        # 检查这位置是不是在 import { ... } 里
        before = line[:col_start]
        between = line[col_start:col_end]
        after = line[col_end:]

        # rule 1: import { X, Y, Z } → 删 X (含逗号)
        if "import" in before and "{" in before and "}" not in before[col_start:]:
            # 找到 X 的 start/end
            # between 应该是 'X' 或 'X '
            if between.strip() == var_name:
                # 删 X + 后面 ',' 或前面 ','
                new_between = between
                if after.startswith(","):
                    new_between = between + ","
                    new_after = after[1:].lstrip()
                elif before.rstrip().endswith(","):
                    new_before = before.rstrip(",").rstrip() + " "
                    new_after = after
                    lines[line_idx] = new_before + new_between + new_after
                    continue
                else:
                    new_after = after.lstrip()
                lines[line_idx] = before.rstrip() + new_after
                continue

        # v2.2.49: skip uppercase first letter (React component 命名约定, 不能改 _)
        # eslint rules-of-hooks 要求 component 名首字母大写
        # 且 default import `import X from 'Y'` JSX 用了 X 但 eslint false positive
        if var_name[0].isupper():
            continue

        # rule 2: 改 catch (e) → catch (_e)
        if "catch" in before and "(" in before and ")" not in before[col_start:]:
            if between.strip() == var_name:
                lines[line_idx] = (
                    before + "_" + between + after
                )
                continue

        # rule 3: 解构赋值 const { X } = ... → _X
        # 简单: 在 col_start 之前插入 '_' (var 名变 _X)
        if between.strip() == var_name:
            # 检查前后是否 var/let/const
            stripped_before = before.rstrip()
            if (
                stripped_before.endswith("var")
                or stripped_before.endswith("let")
                or stripped_before.endswith("const")
                or stripped_before.endswith("=")
            ):
                lines[line_idx] = (
                    before + "_" + between + after
                )
                continue

        # rule 4: skip uppercase (Component function 名)
        if var_name[0].isupper():
            continue

        # fallback: 简单替换 var_name → _var_name
        if between.strip() == var_name:
            lines[line_idx] = (
                line[:col_start] + "_" + var_name + line[col_start + len(var_name):]
            )

    write_file(path, "\n".join(lines))


def main():
    print("=== 1. 跑 eslint 收集 findings ===")
    findings = get_eslint_findings()
    if not findings:
        print("no findings")
        return
    print(f"got {len(findings)} file results")

    print("=== 2. build fix plan (only no-unused-vars) ===")
    plan = build_fix_plan(findings)
    total_edits = sum(len(v) for v in plan.values())
    print(f"plan: {len(plan)} files, {total_edits} edits")

    print("=== 3. apply edits ===")
    for path, edits in plan.items():
        print(f"  {path}: {len(edits)} edits")
        try:
            apply_edits(path, edits)
        except Exception as e:
            print(f"  ERR {path}: {e}")

    print("=== 4. 重新跑 eslint 验证 ===")
    r = subprocess.run(
        ["npx", "eslint", "src"], capture_output=True, text=True
    )
    # 取最后 1 行 summary
    last_lines = r.stdout.strip().split("\n")
    for ln in reversed(last_lines):
        if "problems" in ln:
            print(ln)
            break


if __name__ == "__main__":
    main()
