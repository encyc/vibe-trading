"""
Skill 管理系统

对应 TypeScript 版本的 skills.ts。
实现基于文件系统的 Skill 加载、验证和格式化。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


# =============================================================================
# Constants
# =============================================================================

MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
IGNORE_FILE_NAMES = [".gitignore", ".ignore", ".fdignore"]
CONFIG_DIR_NAME = ".pi"


# =============================================================================
# Types
# =============================================================================


@dataclass
class SkillFrontmatter:
    """Skill 文件的 frontmatter 数据"""

    name: Optional[str] = None
    description: Optional[str] = None
    disable_model_invocation: bool = False


@dataclass
class Skill:
    """
    Skill 定义。

    Attributes:
        name: 唯一标识符 (kebab-case)
        description: 描述（最长 1024 字符）
        file_path: SKILL.md 绝对路径
        base_dir: Skill 所在目录
        source: 来源 ("user" | "project" | "path")
        disable_model_invocation: 是否禁止 LLM 自动调用
    """

    name: str
    description: str
    file_path: str
    base_dir: str
    source: str  # "user" | "project" | "path"
    disable_model_invocation: bool = False


@dataclass
class ResourceDiagnostic:
    """资源诊断信息"""

    type: str  # "warning" | "collision"
    message: str
    path: str
    collision: Optional[Dict[str, Any]] = None


@dataclass
class LoadSkillsResult:
    """加载 Skill 的结果"""

    skills: List[Skill] = field(default_factory=list)
    diagnostics: List[ResourceDiagnostic] = field(default_factory=list)


# =============================================================================
# Frontmatter 解析
# =============================================================================


def parse_frontmatter(content: str) -> Tuple[SkillFrontmatter, str]:
    """
    从 Markdown 文件中解析 YAML frontmatter。

    Args:
        content: 文件内容

    Returns:
        (frontmatter, body) 元组
    """
    frontmatter = SkillFrontmatter()
    body = content

    # 匹配 YAML frontmatter
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if match:
        try:
            yaml_data = yaml.safe_load(match.group(1))
            if isinstance(yaml_data, dict):
                frontmatter.name = yaml_data.get("name")
                frontmatter.description = yaml_data.get("description")
                frontmatter.disable_model_invocation = yaml_data.get(
                    "disable-model-invocation", False
                )
            body = match.group(2)
        except yaml.YAMLError:
            pass

    return frontmatter, body


# =============================================================================
# 验证
# =============================================================================


def _validate_name(name: str, parent_dir_name: str) -> List[str]:
    """验证 Skill 名称"""
    errors = []

    if name != parent_dir_name:
        errors.append(
            f'name "{name}" does not match parent directory "{parent_dir_name}"'
        )

    if len(name) > MAX_NAME_LENGTH:
        errors.append(
            f"name exceeds {MAX_NAME_LENGTH} characters ({len(name)})"
        )

    if not re.match(r"^[a-z0-9-]+$", name):
        errors.append(
            "name contains invalid characters (must be lowercase a-z, 0-9, hyphens only)"
        )

    if name.startswith("-") or name.endswith("-"):
        errors.append("name must not start or end with a hyphen")

    if "--" in name:
        errors.append("name must not contain consecutive hyphens")

    return errors


def _validate_description(description: Optional[str]) -> List[str]:
    """验证 Skill 描述"""
    errors = []

    if not description or not description.strip():
        errors.append("description is required")
    elif len(description) > MAX_DESCRIPTION_LENGTH:
        errors.append(
            f"description exceeds {MAX_DESCRIPTION_LENGTH} characters ({len(description)})"
        )

    return errors


# =============================================================================
# Skill 加载
# =============================================================================


def load_skill_from_file(
    file_path: str, source: str
) -> Tuple[Optional[Skill], List[ResourceDiagnostic]]:
    """
    从单个文件加载 Skill。

    Args:
        file_path: 文件路径
        source: 来源标识

    Returns:
        (skill, diagnostics) 元组
    """
    diagnostics: List[ResourceDiagnostic] = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()

        frontmatter, body = parse_frontmatter(raw_content)
        skill_dir = os.path.dirname(file_path)
        parent_dir_name = os.path.basename(skill_dir)

        # 验证 description
        desc_errors = _validate_description(frontmatter.description)
        for error in desc_errors:
            diagnostics.append(
                ResourceDiagnostic(type="warning", message=error, path=file_path)
            )

        # 使用 frontmatter 名称或回退到父目录名
        name = frontmatter.name or parent_dir_name

        # 验证 name
        name_errors = _validate_name(name, parent_dir_name)
        for error in name_errors:
            diagnostics.append(
                ResourceDiagnostic(type="warning", message=error, path=file_path)
            )

        # 如果没有描述则不加载
        if not frontmatter.description or not frontmatter.description.strip():
            return None, diagnostics

        skill = Skill(
            name=name,
            description=frontmatter.description,
            file_path=file_path,
            base_dir=skill_dir,
            source=source,
            disable_model_invocation=frontmatter.disable_model_invocation,
        )

        return skill, diagnostics

    except Exception as e:
        message = str(e) if str(e) else "failed to parse skill file"
        diagnostics.append(
            ResourceDiagnostic(type="warning", message=message, path=file_path)
        )
        return None, diagnostics


def _load_skills_from_dir_internal(
    dir_path: str,
    source: str,
    include_root_files: bool,
) -> LoadSkillsResult:
    """
    从目录加载 Skills（内部递归函数）。

    发现规则:
    - 根目录的 .md 文件 (include_root_files=True 时)
    - 子目录中的 SKILL.md 文件 (递归)
    """
    skills: List[Skill] = []
    diagnostics: List[ResourceDiagnostic] = []

    if not os.path.exists(dir_path):
        return LoadSkillsResult(skills=skills, diagnostics=diagnostics)

    try:
        entries = os.listdir(dir_path)
    except OSError:
        return LoadSkillsResult(skills=skills, diagnostics=diagnostics)

    for entry_name in sorted(entries):
        # 跳过隐藏文件
        if entry_name.startswith("."):
            continue
        # 跳过 node_modules
        if entry_name == "node_modules":
            continue

        full_path = os.path.join(dir_path, entry_name)

        # 处理符号链接
        try:
            is_dir = os.path.isdir(full_path)
            is_file = os.path.isfile(full_path)
        except OSError:
            continue

        if is_dir:
            sub_result = _load_skills_from_dir_internal(
                full_path, source, include_root_files=False
            )
            skills.extend(sub_result.skills)
            diagnostics.extend(sub_result.diagnostics)
            continue

        if not is_file:
            continue

        is_root_md = include_root_files and entry_name.endswith(".md")
        is_skill_md = not include_root_files and entry_name == "SKILL.md"

        if not is_root_md and not is_skill_md:
            continue

        skill, file_diagnostics = load_skill_from_file(full_path, source)
        diagnostics.extend(file_diagnostics)
        if skill:
            skills.append(skill)

    return LoadSkillsResult(skills=skills, diagnostics=diagnostics)


def load_skills_from_dir(dir_path: str, source: str) -> LoadSkillsResult:
    """
    从目录加载 Skills。

    发现规则:
    - 根目录中的直接 .md 子文件
    - 子目录中递归搜索 SKILL.md

    Args:
        dir_path: 目录路径
        source: 来源标识

    Returns:
        LoadSkillsResult
    """
    return _load_skills_from_dir_internal(dir_path, source, include_root_files=True)


@dataclass
class LoadSkillsOptions:
    """加载 Skills 的选项"""

    cwd: str = ""
    agent_dir: str = ""
    skill_paths: List[str] = field(default_factory=list)
    include_defaults: bool = True


def _get_default_agent_dir() -> str:
    """获取默认的 Agent 配置目录"""
    return os.path.join(os.path.expanduser("~"), CONFIG_DIR_NAME, "agent")


def load_skills(options: Optional[LoadSkillsOptions] = None) -> LoadSkillsResult:
    """
    从所有配置位置加载 Skills。

    加载顺序:
    1. 用户级全局: ~/.pi/agent/skills/
    2. 项目级: <cwd>/.pi/skills/
    3. 显式指定的路径

    Args:
        options: 加载选项

    Returns:
        LoadSkillsResult，包含所有 Skills 和诊断信息
    """
    if options is None:
        options = LoadSkillsOptions()

    cwd = options.cwd or os.getcwd()
    agent_dir = options.agent_dir or _get_default_agent_dir()

    skill_map: Dict[str, Skill] = {}
    real_path_set: set = set()
    all_diagnostics: List[ResourceDiagnostic] = []
    collision_diagnostics: List[ResourceDiagnostic] = []

    def add_skills(result: LoadSkillsResult):
        all_diagnostics.extend(result.diagnostics)
        for skill in result.skills:
            # 解析符号链接检测重复
            try:
                real_path = os.path.realpath(skill.file_path)
            except OSError:
                real_path = skill.file_path

            if real_path in real_path_set:
                continue

            existing = skill_map.get(skill.name)
            if existing:
                collision_diagnostics.append(
                    ResourceDiagnostic(
                        type="collision",
                        message=f'name "{skill.name}" collision',
                        path=skill.file_path,
                        collision={
                            "resource_type": "skill",
                            "name": skill.name,
                            "winner_path": existing.file_path,
                            "loser_path": skill.file_path,
                        },
                    )
                )
            else:
                skill_map[skill.name] = skill
                real_path_set.add(real_path)

    # 默认目录
    if options.include_defaults:
        add_skills(
            _load_skills_from_dir_internal(
                os.path.join(agent_dir, "skills"),
                "user",
                include_root_files=True,
            )
        )
        add_skills(
            _load_skills_from_dir_internal(
                os.path.join(cwd, CONFIG_DIR_NAME, "skills"),
                "project",
                include_root_files=True,
            )
        )

    # 显式路径
    for raw_path in options.skill_paths:
        # 展开 ~
        resolved = os.path.expanduser(raw_path)
        if not os.path.isabs(resolved):
            resolved = os.path.join(cwd, resolved)

        if not os.path.exists(resolved):
            all_diagnostics.append(
                ResourceDiagnostic(
                    type="warning",
                    message="skill path does not exist",
                    path=resolved,
                )
            )
            continue

        try:
            if os.path.isdir(resolved):
                add_skills(
                    _load_skills_from_dir_internal(
                        resolved, "path", include_root_files=True
                    )
                )
            elif os.path.isfile(resolved) and resolved.endswith(".md"):
                skill, diags = load_skill_from_file(resolved, "path")
                if skill:
                    add_skills(
                        LoadSkillsResult(skills=[skill], diagnostics=diags)
                    )
                else:
                    all_diagnostics.extend(diags)
            else:
                all_diagnostics.append(
                    ResourceDiagnostic(
                        type="warning",
                        message="skill path is not a markdown file",
                        path=resolved,
                    )
                )
        except Exception as e:
            all_diagnostics.append(
                ResourceDiagnostic(
                    type="warning",
                    message=str(e),
                    path=resolved,
                )
            )

    return LoadSkillsResult(
        skills=list(skill_map.values()),
        diagnostics=all_diagnostics + collision_diagnostics,
    )


# =============================================================================
# Skill 格式化 (注入 System Prompt)
# =============================================================================


def _escape_xml(s: str) -> str:
    """XML 转义"""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def format_skills_for_prompt(skills: List[Skill]) -> str:
    """
    将 Skills 格式化为 System Prompt 中的 XML 片段。

    遵循 Agent Skills 标准 (https://agentskills.io/integrate-skills)。
    disable_model_invocation=True 的 Skill 会被排除。

    Args:
        skills: Skill 列表

    Returns:
        格式化后的 XML 字符串
    """
    visible_skills = [s for s in skills if not s.disable_model_invocation]

    if not visible_skills:
        return ""

    lines = [
        "\n\nThe following skills provide specialized instructions for specific tasks.",
        "Use the read tool to load a skill's file when the task matches its description.",
        "When a skill file references a relative path, resolve it against the skill "
        "directory (parent of SKILL.md / dirname of the path) and use that absolute "
        "path in tool commands.",
        "",
        "<available_skills>",
    ]

    for skill in visible_skills:
        lines.append("  <skill>")
        lines.append(f"    <name>{_escape_xml(skill.name)}</name>")
        lines.append(
            f"    <description>{_escape_xml(skill.description)}</description>"
        )
        lines.append(
            f"    <location>{_escape_xml(skill.file_path)}</location>"
        )
        lines.append("  </skill>")

    lines.append("</available_skills>")

    return "\n".join(lines)
