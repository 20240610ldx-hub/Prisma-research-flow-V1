#!/usr/bin/env python3
"""
.claude/hooks/preflight_check.py
触发:UserPromptSubmit (匹配 ^/deep-research)

v3 升级:
- UTF-8 强制
- 检查 PLANNER_API_KEY (xinghuapi) 而非 GLM_API_KEY
- 8 个 Tavily Key 检测
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

# UTF-8 强制
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def get_env_value(env_text: str, key: str) -> str:
    for line in env_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def check():
    errors = []
    warnings = []

    # 1. .env
    env_path = Path(".env")
    if not env_path.exists():
        errors.append(".env 不存在,请 cp .env.example .env 并填入 API keys")
    else:
        env_text = env_path.read_text(encoding="utf-8", errors="replace")

        # 必需:LLM 规划层 API key
        planner_keys = ["PLANNER_API_KEY", "XINGHUA_API_KEY", "ANTHROPIC_API_KEY"]
        if not any(get_env_value(env_text, k) for k in planner_keys):
            errors.append(
                "未配置 LLM 规划层 API key (PLANNER_API_KEY / XINGHUA_API_KEY / ANTHROPIC_API_KEY 任一)"
            )

        # Tavily key 数量
        tavily_count = sum(
            1 for i in range(1, 9) if get_env_value(env_text, f"TAVILY_API_KEY_{i}")
        )
        if tavily_count == 0:
            warnings.append("未配置任何 TAVILY_API_KEY,web-researcher 将仅用 Claude Code 内置 WebSearch")
        elif tavily_count < 4:
            warnings.append(f"仅配置 {tavily_count} 个 Tavily Key,建议 6-8 个以支持高并发")
        else:
            warnings.append(f"已配置 {tavily_count} 个 Tavily Key (推荐 6-8 个)")

    # 2. scripts
    if not Path("scripts").is_dir():
        errors.append("scripts/ 缺失")
    else:
        for s in ["llm_plan.py", "llm_queries.py", "tavily_search.py", "_utils.py"]:
            if not Path(f"scripts/{s}").exists():
                errors.append(f"scripts/{s} 缺失")

    # 3. 输出目录
    for d in ["output", "findings"]:
        Path(d).mkdir(parents=True, exist_ok=True)
        if not os.access(d, os.W_OK):
            errors.append(f"{d}/ 不可写")

    # 4. Python 依赖
    missing = []
    for mod in ["openai", "tavily", "dotenv"]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        errors.append(f"Python 依赖缺失: {', '.join(missing)} (pip install -r requirements.txt)")

    # 5. tenacity (软依赖,缺失只警告)
    try:
        import tenacity  # noqa
    except ImportError:
        warnings.append("tenacity 未安装,网络重试将降级为简单循环 (建议 pip install tenacity)")

    if errors:
        msg = "❌ Preflight 阻断:\n" + "\n".join(f"  - {e}" for e in errors)
        print(msg, file=sys.stderr)
        sys.exit(2)

    extra = ""
    if warnings:
        extra = "\n[Preflight 提示]\n" + "\n".join(f"  · {w}" for w in warnings)

    print(json.dumps({
        "additionalContext": (
            "[Preflight OK] 环境就绪。" + extra +
            "\n\n关键纪律:严格按 /deep-research 阶段顺序;"
            "Plan 必须先在对话中展示并等待用户确认 [1]/[2]/[3] 后才写入 plan.md;"
            "web-researcher 必须并行 spawn,不得串行。"
        )
    }, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    check()
