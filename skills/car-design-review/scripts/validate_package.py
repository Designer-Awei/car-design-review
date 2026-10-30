#!/usr/bin/env python3
"""Check the portable package and original references using only the standard library."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


def validate(root):
    root = root.resolve()
    failures = []
    required = ["SKILL.md", "agents/openai.yaml", "references/originals/manifest.json",
                "references/originals/PFDBI-framework.pdf", "references/writing-method.md",
                "references/document-structure.md", "references/delivery-adapters.md",
                "assets/templates/document.md", "assets/templates/research-ledger.json",
                "assets/templates/evolution-run.json", "evolution/README.md", "evolution/principles.md",
                "evolution/index.json", "scripts/record_run.py"]
    for name in required:
        if not (root / name).is_file():
            failures.append("缺少文件：" + name)
    if not (root / "SKILL.md").is_file():
        return failures
    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    front = re.match(r"\A---\n(.*?)\n---\n", skill, re.S)
    if not front:
        failures.append("SKILL.md缺少有效frontmatter")
    else:
        name = re.search(r"^name:\s*(\S+)\s*$", front[1], re.M)
        description = re.search(r"^description:\s*(.+)$", front[1], re.M)
        if not name or not re.fullmatch(r"[a-z0-9-]{1,64}", name[1]) or name[1] != root.name:
            failures.append("skill名称与目录不一致或格式无效")
        if not description or len(description[1]) > 1024:
            failures.append("description为空或过长")
    if len(skill.splitlines()) > 500:
        failures.append("SKILL.md超过500行，应拆分参考资料")
    checked_links = 0
    for path in root.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if "\ufffd" in text:
            failures.append("存在替换字符，检查编码：" + path.relative_to(root).as_posix())
        for raw in re.findall(r"\[[^\]]*\]\(([^\n)]+)\)", text):
            target = raw.strip().strip("<>")
            # Template image paths and URLs are deliberately filled at invocation.
            if path.is_relative_to(root / "assets/templates") and re.fullmatch(r"\{\{[^{}]+\}\}", target):
                continue
            if target.startswith("#") or urlsplit(target).scheme:
                continue
            target = unquote(target.split("#", 1)[0])
            if not target:
                continue
            dest = (path.parent / target).resolve()
            if not dest.is_relative_to(root):
                failures.append(f"引用超出skill目录：{path.name} -> {target}")
            elif not dest.exists():
                failures.append(f"无效本地链接：{path.relative_to(root)} -> {target}")
            checked_links += 1
    try:
        manifest = json.loads((root / "references/originals/manifest.json").read_text(encoding="utf-8"))
        materials = manifest["materials"]
        originals = root / "references/originals"
        for item in materials:
            path = (originals / item["path"]).resolve()
            if not path.is_relative_to(originals):
                failures.append("原件索引路径超界")
                continue
            blob = path.read_bytes()
            if len(blob) != item["bytes"] or sha256(blob).hexdigest() != item["sha256"]:
                failures.append("原件字节数或SHA-256不匹配：" + item["path"])
        if len([x for x in materials if x["kind"] == "user_attachment"]) != 3:
            failures.append("应保留三篇完整ToTo原文附件")
        if not (originals / "PFDBI-framework.pdf").read_bytes().startswith(b"%PDF-"):
            failures.append("PFDBI不是有效PDF文件头")
        index = json.loads((root / "evolution/index.json").read_text(encoding="utf-8"))
        ids = []
        for run in index["runs"]:
            ids.append(run["run_id"])
            path = (root / "evolution" / run["path"]).resolve()
            if not path.is_relative_to(root / "evolution") or not path.is_file():
                failures.append("迭代记录不存在或路径超界：" + run["run_id"])
        if len(ids) != len(set(ids)):
            failures.append("迭代索引存在重复ID")
        metadata = (root / "agents/openai.yaml").read_text(encoding="utf-8")
        if "$car-design-review" not in metadata:
            failures.append("UI默认提示词没有调用本skill")
        for path in (root / "assets/templates").glob("*.json"):
            json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError, TypeError) as error:
        failures.append("资源校验失败：" + str(error))
    print(f"已检查{checked_links}个本地引用；参考原件、模板与迭代索引已核验。")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        errors = validate(args.skill_root)
    except (OSError, ValueError) as error:
        errors = [str(error)]
    if errors:
        for error in errors:
            print("FAIL: " + error, file=sys.stderr)
        return 1
    print("PASS：包结构、资源路径与原始参考完整性通过。此检查不替代文案与排版审核。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
