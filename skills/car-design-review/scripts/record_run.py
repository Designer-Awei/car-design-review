#!/usr/bin/env python3
"""Record one invocation locally; never publish or rewrite stable principles."""
import argparse
from datetime import date
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

LIST_FIELDS = ("tags", "formats", "user_feedback", "changes", "validation", "evidence",
               "candidate_improvements", "promoted_principles", "limitations")
HEADINGS = {
    "user_feedback": "用户反馈（未收到时留空，不虚构）",
    "changes": "问题与采取的修改",
    "validation": "验证结果",
    "evidence": "证据与可定位的成果",
    "candidate_improvements": "候选改进（尚未提升为通用规则）",
    "promoted_principles": "本次已确认的可复用原则（实际规则另行审阅更新）",
    "limitations": "限制与待办",
}
REQUIRED = {"run_id", "date", "task", "tags", "formats", "status", "outcome", *HEADINGS}


def validate(data):
    if not isinstance(data, dict):
        raise ValueError("记录必须是JSON对象")
    missing, extra = REQUIRED - data.keys(), data.keys() - REQUIRED
    if missing or extra:
        raise ValueError(f"字段不匹配：缺少{sorted(missing)}，未知{sorted(extra)}")
    for key in ("run_id", "date", "task", "status", "outcome"):
        if not isinstance(data[key], str) or not data[key].strip():
            raise ValueError(f"{key} 必须为非空字符串")
    date.fromisoformat(data["date"])
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]{0,99}", data["run_id"]):
        raise ValueError("run_id须为YYYY-MM-DD-小写英文任务标识，只允许数字和连字符")
    if not data["run_id"].startswith(data["date"] + "-"):
        raise ValueError("run_id与date的日期必须一致")
    if data["status"] not in {"complete", "partial", "blocked"}:
        raise ValueError("status只能是complete、partial或blocked")
    for key in LIST_FIELDS:
        if not isinstance(data[key], list) or any(not isinstance(v, str) or not v.strip() for v in data[key]):
            raise ValueError(f"{key} 必须为字符串数组，可留空")
    return data


def render(data):
    text = [f'# {data["task"]}', "", f'- 记录ID：{data["run_id"]}', f'- 日期：{data["date"]}',
            f'- 状态：{data["status"]}', f'- 标签：{", ".join(data["tags"]) or "无"}',
            f'- 格式：{", ".join(data["formats"]) or "未指定"}', "", "## 效果", "", data["outcome"], ""]
    for key, heading in HEADINGS.items():
        text += ["## " + heading, ""]
        text += ["- " + value.replace("\n", "\n  ") for value in data[key]] or ["未记录。"]
        text.append("")
    return "\n".join(text)


def record(skill, data):
    skill = skill.resolve()
    if not (skill / "SKILL.md").is_file():
        raise ValueError("skill目录中没有SKILL.md")
    evolution = skill / "evolution"
    runs = evolution / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    lock = evolution / ".record.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError("已有记录任务正在写入，或留下了锁文件；先核实该任务状态再处理") from None
    os.close(fd)
    temp = evolution / (".index-" + uuid4().hex + ".tmp")
    dest = runs / (data["run_id"] + ".md")
    created = False
    try:
        index_path = evolution / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"schema_version": 1, "runs": []}
        if index.get("schema_version") != 1 or not isinstance(index.get("runs"), list):
            raise ValueError("现有index.json格式不支持，未修改")
        if dest.exists() or any(r.get("run_id") == data["run_id"] for r in index["runs"]):
            raise ValueError("run_id已经存在；为新一次调用使用新标识，不覆盖历史")
        with dest.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(render(data))
        created = True
        index["runs"].append({"run_id": data["run_id"], "date": data["date"], "task": data["task"],
                              "tags": data["tags"], "status": data["status"],
                              "path": dest.relative_to(evolution).as_posix()})
        index["runs"].sort(key=lambda r: (r["date"], r["run_id"]), reverse=True)
        temp.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(index_path)
    except Exception:
        if created:
            dest.unlink(missing_ok=True)
        raise
    finally:
        temp.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)
    return dest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="填写后的evolution-run.json，UTF-8")
    parser.add_argument("--skill-root", type=Path, default=Path(__file__).resolve().parents[1], help="默认本脚本所在skill，可指定副本用于验证")
    args = parser.parse_args()
    try:
        data = validate(json.loads(args.input.read_text(encoding="utf-8-sig")))
        dest = record(args.skill_root, data)
    except (ValueError, OSError) as error:
        print("记录失败：" + str(error), file=sys.stderr)
        return 2
    print("已记录：" + str(dest))
    print("已更新evolution/index.json；未改写稳定规则，未执行网络操作。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
