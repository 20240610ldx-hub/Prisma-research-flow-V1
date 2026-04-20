#!/usr/bin/env python3
"""
.claude/hooks/post_write_check.py
触发:PostToolUse (matcher: Write)
v3.1:slug 感知 — 自动定位正确的 output/<slug>/ 目录检查文件
"""
from __future__ import annotations
import json, os, re, sys
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


def safe_read(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def check_findings_json(path):
    issues = []
    text = safe_read(path)
    if not text.strip():
        return [f"{path.name} 为空"]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return [f"{path.name} 不是合法 JSON: {e}"]
    if not isinstance(data, dict):
        return [f"{path.name} 根对象不是 dict"]
    for field in ["sub_id", "findings"]:
        if field not in data:
            issues.append(f"{path.name} 缺字段: {field}")
    findings = data.get("findings", [])
    if not isinstance(findings, list):
        issues.append(f"{path.name} findings 不是数组")
    elif len(findings) < 3:
        issues.append(f"{path.name} 只有 {len(findings)} 条 findings (建议 ≥6)")
    for i, f in enumerate(findings):
        if not isinstance(f, dict): continue
        for key in ["claim", "source_url", "quote"]:
            if not f.get(key):
                issues.append(f"{path.name} 第{i+1}条缺 {key}")
                break
        url = f.get("source_url", "")
        if url and not url.startswith("http"):
            issues.append(f"{path.name} 第{i+1}条 URL 异常: {url[:50]}")
    return issues


def check_plan_md(path):
    issues = []
    text = safe_read(path)
    for sec in ["研究主体界定", "多维技术拆解", "关键数据需求"]:
        if sec not in text:
            issues.append(f"plan.md 缺章节: {sec}")
    dims = re.findall(r"维度\s*[ABCD一二三四]", text)
    if len(set(dims)) < 3:
        issues.append(f"plan.md 只检测到 {len(set(dims))} 个维度 (期望 4)")
    return issues


def check_analysis_md(path):
    text = safe_read(path)
    last = "\n".join(text.rstrip().splitlines()[-5:])
    return [] if "[VERDICT:" in last else ["analysis.md 末尾缺 [VERDICT: COMPLETE|NEEDS_MORE]"]


def check_report_draft(path):
    issues = []
    text = safe_read(path)
    if "执行摘要" not in text and "Executive Summary" not in text:
        issues.append("缺「执行摘要」")
    if "结论" not in text and "Conclusion" not in text:
        issues.append("缺「结论」")
    tables = re.findall(r"\n\|[^\n]+\|\n\|[\s\-:|]+\|", text)
    if len(tables) < 3:
        issues.append(f"表格 {len(tables)} 个 (硬性 ≥3)")
    n = len(text)
    if n < 3000:
        issues.append(f"过短: {n} 字符 (建议 ≥5000)")
    # 拒绝词
    banned = ["随着...的发展", "随着…的发展", "值得关注", "不断提升", "日益增强",
              "取得显著成效", "综上所述", "毋庸置疑", "本报告旨在分析", "全军覆没"]
    found = [w for w in banned if w in text]
    if found:
        issues.append(f"拒绝词: {', '.join(found)}")
    # 套话词上限
    overused = [("结构性", 5), ("悖论", 4), ("僵局", 3), ("棘轮效应", 2)]
    hits = [(w, text.count(w)) for w, lim in overused if text.count(w) > lim]
    if hits:
        issues.append("套话词超限: " + ", ".join(f"{w}({c}次)" for w, c in hits))
    # 引用密度
    cite = (len(re.findall(r"\[[\w\.\-]+\.[a-z]{2,}\]", text))
            + len(re.findall(r"\(\w[^)]{1,40},\s*\d{4}\)", text)))
    expected = n // 800
    if cite < expected:
        issues.append(f"引用密度低: {cite} 处 / {n} 字符 (期望 ≥{expected})")
    return issues


def main():
    try:
        hook_data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    file_path = hook_data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    path = Path(file_path)
    if not path.exists():
        sys.exit(0)

    p_str = str(path).replace("\\", "/")
    slug = get_current_slug()

    issues = []

    # Bug 1 防御:检测到 findings/<file>.json 却不在 slug 子目录时报警
    if "findings/" in p_str and path.suffix == ".json":
        # 规范化路径
        parts = p_str.replace("\\", "/").split("/")
        try:
            idx = parts.index("findings")
            # 正确路径:findings/<slug>/<file>.json (parts[idx+1] 是 slug)
            # 错误路径:findings/<file>.json (parts[idx+1] 以 .json 结尾)
            if idx + 1 < len(parts):
                next_part = parts[idx + 1]
                if next_part.endswith(".json") and slug:
                    issues.append(
                        f"⚠ 路径错误:写入了 findings/{next_part} (旧硬编码路径),"
                        f"正确路径应为 findings/{slug}/{next_part}。"
                        f"请立即重新写入正确位置,并删除错误文件。"
                    )
        except ValueError:
            pass
        issues.extend(check_findings_json(path))
    elif path.name == "plan.md":
        issues = check_plan_md(path)
    elif path.name == "analysis.md":
        issues = check_analysis_md(path)
    elif path.name == "report_draft.md":
        issues = check_report_draft(path)
    else:
        sys.exit(0)

    if issues:
        print(json.dumps({
            "additionalContext": (
                f"[post_write_check on {path.name}]"
                + (f" (slug={slug})" if slug else "") + "\n"
                + "\n".join(f"  - {i}" for i in issues)
            )
        }, ensure_ascii=False))

    sys.exit(0)

if __name__ == "__main__":
    main()
