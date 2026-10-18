"""Progressive-disclosure skill loader (guide 7.2).

L1 at startup: only name + description from each SKILL.md frontmatter.
L2 when a task matches: the full SKILL.md body goes into the system prompt.
L3 on demand: references/* through read_reference(name).
Scripts are imported as tool functions and stay runnable from the command line.
"""
from __future__ import annotations

import importlib.util
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

log = logging.getLogger("fasalnama.skills")
SKILLS_ROOT = Path(__file__).resolve().parents[1] / "skill"
_WORD_RE = re.compile(r"[a-z]{4,}")


@dataclass(frozen=True)
class SkillMeta:
    name: str
    description: str
    path: Path


@dataclass
class DisclosureLog:
    levels: list[str] = field(default_factory=list)

    def record(self, level: str) -> None:
        self.levels.append(level)
        log.info("skill disclosure: %s", level)


def read_frontmatter(skill_md: Path) -> dict[str, str]:
    """Read ONLY the frontmatter block (stops at the closing ---). Top-level keys only."""
    out: dict[str, str] = {}
    with skill_md.open(encoding="utf-8") as fh:
        if fh.readline().strip() != "---":
            raise ValueError(f"{skill_md} has no frontmatter")
        for line in fh:
            if line.strip() == "---":
                return out
            if line[:1].isspace() or ":" not in line:
                continue
            key, value = line.split(":", 1)
            out[key.strip()] = value.strip().strip('"').strip("'")
    raise ValueError(f"{skill_md} frontmatter is not closed")


def _body(skill_md: Path) -> str:
    text = skill_md.read_text(encoding="utf-8").replace("\r\n", "\n")
    parts = text.split("\n---\n", 1)
    return parts[1].strip() if len(parts) == 2 else text


class SkillLoader:
    def __init__(self, root: Path = SKILLS_ROOT) -> None:
        self.root = root
        self.log = DisclosureLog()
        self.skills: dict[str, SkillMeta] = {}
        for skill_md in sorted(root.glob("*/SKILL.md")):
            fm = read_frontmatter(skill_md)
            name = fm.get("name", "")
            if name != skill_md.parent.name:
                log.warning("skipping %s: name does not match folder", skill_md)
                continue
            self.skills[name] = SkillMeta(name, fm.get("description", ""), skill_md.parent)
        self.log.record("L1:frontmatter")

    def match(self, task: str) -> SkillMeta | None:
        words = set(_WORD_RE.findall(task.lower()))
        best, best_score = None, 0
        for meta in self.skills.values():
            score = len(words & set(_WORD_RE.findall(meta.description.lower())))
            if score > best_score:
                best, best_score = meta, score
        return best

    def load_body(self, meta: SkillMeta) -> str:
        self.log.record(f"L2:body:{meta.name}")
        return _body(meta.path / "SKILL.md")

    def list_references(self, meta: SkillMeta) -> list[str]:
        return sorted(p.name for p in (meta.path / "references").glob("*.md"))

    def read_reference(self, meta: SkillMeta, name: str) -> str:
        if not name.endswith(".md"):
            name += ".md"
        ref_dir = (meta.path / "references").resolve()
        target = (ref_dir / name).resolve()
        if target.parent != ref_dir or not target.is_file():
            raise FileNotFoundError(f"unknown reference: {name}")
        self.log.record(f"L3:reference:{name}")
        return target.read_text(encoding="utf-8")

    def load_script(self, meta: SkillMeta, script: str) -> ModuleType:
        scripts_dir = meta.path / "scripts"
        path = scripts_dir / f"{script}.py"
        if not path.is_file():
            raise FileNotFoundError(f"unknown script: {script}")
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        spec = importlib.util.spec_from_file_location(f"skill_{meta.name.replace('-', '_')}_{script}", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.log.record(f"script:{script}")
        return module