#!/usr/bin/env python3
"""
.claude/hooks/pre_write_check.py
触发:PreToolUse (matcher: Write)
v3.1:slug 感知 — 检查 output/<slug>/.plan_confirmed 或兜底 output/.plan_confirmed
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def get_current_slug():
    marker = Path("output/.current_slug")
    if marker.exists():
        s = marker.read_text(encoding="utf-8").strip()
        if s: return s
    output_dir = Path("output")
    if not output_dir.exists(): return None
    dirs = [d for d in output_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    return max(dirs, key=lambda d: d.stat().st_mtime).name if dirs else None


def is_confirmed(slug):
    if slug and Path(f"output/{slug}/.plan_confirmed").exists():
        return True
    return Path("output/.plan_confirmed").exists()


def main():
    try:
        hook_data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    file_path = hook_data.get("tool_input", {}).get("file_path", "")
    norm = file_path.replace("\\", "/")
    if not (norm.endswith("/plan.md") or norm.endswith("plan.md")):
        sys.exit(0)

    slug = get_current_slug()
    if is_confirmed(slug):
        sys.exit(0)

    slug_hint = f"output/{slug}/" if slug else "output/"
    # 跨平台单命令(避免 touch/type nul 双命令混乱)
    confirmed_cmd = f"python -c \"import pathlib; pathlib.Path('{slug_hint}.plan_confirmed').touch()\""

    msg = (
        f"[pre_write_check 阻断] 用户尚未确认研究计划,不能写入 plan.md。\n\n"
        f"正确流程:\n"
        f"  1. 调用 llm_plan.py 把草案 print 到 stdout\n"
        f"  2. 在对话中展示完整草案 + 以下选项框:\n"
        f"     ---\n"
        f"     请选择:\n"
        f"       [1] 确认,开始深度研究\n"
        f"       [2] 修改某个维度\n"
        f"       [3] 追加新要求\n"
        f"     ---\n"
        f"  3. 等用户明确回复 1/2/3\n"
        f"  4. 用户确认后,执行(跨平台单命令):\n"
        f"     Bash: {confirmed_cmd}\n"
        f"     然后再 Write plan.md"
    )
    print(json.dumps({"decision": "block", "reason": msg}, ensure_ascii=False))
    sys.exit(0)

if __name__ == "__main__":
    main()
