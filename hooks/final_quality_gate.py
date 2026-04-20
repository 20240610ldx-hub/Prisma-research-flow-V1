#!/usr/bin/env python3
"""
.claude/hooks/final_quality_gate.py
触发:Stop hook
v3.1:slug 感知 + 软告警 + 60s 异步等待
"""
from __future__ import annotations
import json, os, re, sys, time
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

STATE_FILE = Path(".claude/hooks/.quality_gate_state.json")  # 兼容旧路径,实际用 _get_state_file(slug)
MAX_HARD_BLOCKS = 1
WAIT_TIMEOUT = 30    # 信号驱动的上限(不再是 busy-wait 60s)


def get_current_slug():
    marker = Path("output/.current_slug")
    if marker.exists():
        s = marker.read_text(encoding="utf-8").strip()
        if s: return s
    output_dir = Path("output")
    if not output_dir.exists(): return None
    dirs = [d for d in output_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    return max(dirs, key=lambda d: d.stat().st_mtime).name if dirs else None


def _get_state_file(slug):
    """每个 slug 一个独立的状态文件,避免跨任务污染"""
    if slug:
        return Path(f"output/{slug}/.quality_gate_state.json")
    return Path(".claude/hooks/.quality_gate_state.json")


def load_state(slug=None):
    f = _get_state_file(slug)
    try:
        return json.loads(f.read_text()) if f.exists() else {}
    except Exception:
        return {}


def save_state(s, slug=None):
    f = _get_state_file(slug)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(s))


def safe_read(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def count_valid_findings(slug):
    """统计 findings/<slug>/ 或 findings/ 下有效 JSON 数"""
    dirs_to_check = []
    if slug:
        dirs_to_check.append(Path(f"findings/{slug}"))
    dirs_to_check.append(Path("findings"))

    for d in dirs_to_check:
        if not d.exists():
            continue
        n = 0
        for p in d.glob("*.json"):
            try:
                data = json.loads(safe_read(p))
                if isinstance(data.get("findings"), list) and len(data["findings"]) >= 1:
                    n += 1
            except Exception:
                continue
        if n > 0:
            return n
    return 0


def _newest_finding_mtime(slug):
    """返回 findings/<slug>/ 下最新 JSON 的修改时间(秒),没有文件则返回 0"""
    dirs_to_check = []
    if slug:
        dirs_to_check.append(Path(f"findings/{slug}"))
    dirs_to_check.append(Path("findings"))

    newest = 0.0
    for d in dirs_to_check:
        if not d.exists():
            continue
        for p in d.glob("*.json"):
            m = p.stat().st_mtime
            if m > newest:
                newest = m
    return newest


def wait_for_findings(slug, min_count, timeout):
    """
    信号驱动等待:只要 findings 还在陆续写入(最近写入 <10s 前)就继续等,
    否则立即返回。避免无脑 60s busy-wait。
    """
    deadline = time.time() + timeout
    poll_interval = 2
    quiet_threshold = 10  # 最近 10 秒无新文件 = 认为 agent 已停

    while time.time() < deadline:
        n = count_valid_findings(slug)
        if n >= min_count:
            return n
        newest = _newest_finding_mtime(slug)
        if newest == 0 or (time.time() - newest > quiet_threshold):
            # 没有文件 或者 最近10秒没新文件 → 不再等
            return n
        time.sleep(poll_interval)
    return count_valid_findings(slug)


def check_outputs(slug):
    """返回 (critical_problems, warnings)"""
    critical, warnings = [], []

    # 路径:优先 slug 子目录,兜底旧路径
    def find_file(name):
        if slug:
            p = Path(f"output/{slug}/{name}")
            if p.exists(): return p
        p = Path(f"output/{name}")
        return p if p.exists() else None

    plan = find_file("plan.md")
    analysis = find_file("analysis.md")
    draft = find_file("report_draft.md")
    final = find_file("report_final.md")
    findings_n = count_valid_findings(slug)

    if not plan and findings_n == 0:
        critical.append("既无 plan.md 也无 findings — 工作流未启动")

    if not plan:   warnings.append("plan.md 不存在")
    if findings_n < 3: warnings.append(f"findings 仅 {findings_n} 个 (建议 ≥3)")
    if plan and findings_n >= 3 and not analysis:
        warnings.append("有 findings 但无 analysis.md")
    if not draft and not final:
        warnings.append("无 report_draft.md / report_final.md — synthesizer 未运行")
    elif draft and not final:
        warnings.append("仅有 draft 无 final — apply_citations.py 未运行(请手动执行)")

    if final:
        text = safe_read(final)
        if len(text) < 3000: warnings.append(f"final 报告偏短: {len(text)} 字符")
        tables = re.findall(r"\n\|[^\n]+\|\n\|[\s\-:|]+\|", text)
        if len(tables) < 3: warnings.append(f"表格 {len(tables)} 个 (建议 ≥3)")
        if "References" not in text and "参考来源" not in text:
            warnings.append("final 报告缺 References 段")

    return critical, warnings


def is_in_research_context():
    """
    判断当前 Stop 事件是否源自 /deep-research 工作流。
    
    判断依据:output/.current_slug 文件存在 且 对应 slug 目录存在。
    其他场景(比如普通对话、调试会话)Stop 时不应触发质量门。
    """
    marker = Path("output/.current_slug")
    if not marker.exists():
        return False
    try:
        slug = marker.read_text(encoding="utf-8").strip()
    except Exception:
        return False
    if not slug:
        return False
    slug_dir = Path(f"output/{slug}")
    return slug_dir.exists() and slug_dir.is_dir()


def main():
    # Bug 4 修复:非研究上下文直接放行
    if not is_in_research_context():
        sys.exit(0)

    state = load_state(slug)
    block_count = state.get("block_count", 0)
    # slug 已在上方 is_in_research_context 里校验过,此处重新取一次
    slug_file = Path("output/.current_slug")
    slug = slug_file.read_text(encoding="utf-8").strip() if slug_file.exists() else get_current_slug()

    findings_n = count_valid_findings(slug)
    plan_exists = Path(f"output/{slug}/plan.md").exists() if slug else Path("output/plan.md").exists()

    if findings_n < 3 and plan_exists:
        print(f"[quality_gate] findings={findings_n},等最多 {WAIT_TIMEOUT}s...", file=sys.stderr)
        wait_for_findings(slug, min_count=3, timeout=WAIT_TIMEOUT)

    critical, warnings = check_outputs(slug)

    if not critical:
        save_state({"block_count": 0}, slug)
        if warnings:
            print(
                "[quality_gate WARNING] 工作流完成,注意以下问题(放行):\n"
                + "\n".join(f"  · {w}" for w in warnings),
                file=sys.stderr
            )
        sys.exit(0)

    if block_count >= MAX_HARD_BLOCKS:
        save_state({"block_count": 0}, slug)
        print(f"[quality_gate] 已阻断 {MAX_HARD_BLOCKS} 次,放行。问题:\n"
              + "\n".join(f"  - {p}" for p in critical + warnings), file=sys.stderr)
        sys.exit(0)

    state["block_count"] = block_count + 1
    save_state(state, slug)

    feedback = (
        f"[Quality Gate 阻断 #{block_count+1}/{MAX_HARD_BLOCKS}] 关键产出缺失:\n"
        + "\n".join(f"  - {p}" for p in critical)
        + ("\n\n提示:\n" + "\n".join(f"  · {w}" for w in warnings) if warnings else "")
        + "\n\n请修正后再尝试结束。"
    )
    print(json.dumps({"decision": "block", "reason": feedback}, ensure_ascii=False))
    sys.exit(0)

if __name__ == "__main__":
    main()
