#!/usr/bin/env python3
"""
.claude/hooks/post_task_log.py
触发:PostToolUse (matcher: Task)

记录 subagent 调用日志 + 检查 web-researcher 产出量。
v3: UTF-8 强制 + 全异常吞噬(永不阻断主流程)
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    try:
        hook_data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    try:
        tool_input = hook_data.get("tool_input", {})
        tool_response = hook_data.get("tool_response", {})

        subagent_type = tool_input.get("subagent_type", "unknown")
        prompt_preview = (tool_input.get("prompt", "")[:200]).replace("\n", " ")

        response_text = ""
        if isinstance(tool_response, dict):
            content = tool_response.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        response_text += block.get("text", "")
            elif isinstance(content, str):
                response_text = content
        response_preview = response_text[:300].replace("\n", " ")

        # 确定 log 路径(绝对路径,避免 Windows 相对路径失效)
        # 优先写到 output/<slug>/workflow.log,找不到 slug 时写 output/workflow.log
        cwd = Path.cwd()
        output_base = cwd / "output"
        log_path = None
        # 找最新的 slug 子目录
        if output_base.exists():
            slug_dirs = [d for d in output_base.iterdir() if d.is_dir() and not d.name.startswith('.')]
            if slug_dirs:
                latest_slug_dir = max(slug_dirs, key=lambda d: d.stat().st_mtime)
                log_path = latest_slug_dir / "workflow.log"
        if log_path is None:
            output_base.mkdir(parents=True, exist_ok=True)
            log_path = output_base / "workflow.log"

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_line = (
            f"[{timestamp}] subagent={subagent_type} | "
            f"prompt={prompt_preview[:150]} | "
            f"response={response_preview[:200]}\n"
        )
        with log_path.open("a", encoding="utf-8") as f:
            f.write(log_line)

        # 检查 web-researcher 产出
        feedback = []
        if subagent_type == "web-researcher":
            findings_dir = Path("findings")
            if findings_dir.exists():
                json_files = list(findings_dir.glob("*.json"))
                if json_files:
                    latest = max(json_files, key=lambda p: p.stat().st_mtime)
                    try:
                        data = json.loads(latest.read_text(encoding="utf-8", errors="replace"))
                        f_count = len(data.get("findings", []))
                        if f_count < 3:
                            feedback.append(
                                f"researcher {data.get('sub_id', '?')} 仅产出 {f_count} 条 findings"
                            )
                    except Exception:
                        pass

        if feedback:
            print(json.dumps({
                "additionalContext": "[post_task_log]\n" + "\n".join(f"  - {i}" for i in feedback)
            }, ensure_ascii=False))

    except Exception as e:
        # 永不阻断
        print(f"[post_task_log] 内部异常(已吞): {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
