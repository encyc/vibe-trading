#!/usr/bin/env python3
"""
检查所有Agent的tools使用情况
"""
import asyncio
import sys
sys.path.insert(0, 'backend/src')

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

# 检查点
checklist = []

# =============================================================================
# 1. 检查Agent创建时是否赋予tools
# =============================================================================
console.print("[bold cyan]1. 检查Agent创建时是否赋予tools[/bold cyan]")

from vibe_trading.agents.agent_factory import create_trading_agent, ToolContext, AgentConfig

tool_context = ToolContext(symbol="BTCUSDT", interval="30m")

async def check_agent_tools():
    config = AgentConfig(name="Test", role="technical_analyst")
    agent = await create_trading_agent(config, tool_context)

    # 检查agent的tools
    agent_tools = agent.state.get("tools", [])
    if agent_tools:
        console.print(f"  ✅ Agent有 {len(agent_tools)} 个tools")
        for tool in agent_tools[:3]:
            console.print(f"     - {tool.get('name', 'unknown')}")
    else:
        console.print("  [red]❌ Agent的tools为空！[/red]")

    checklist.append(("Agent tools", len(agent_tools) > 0))

# =============================================================================
# 2. 检查tools模块中的函数是否被调用
# =============================================================================
console.print("\n[bold cyan]2. 检查tools模块函数是否被调用[/bold cyan]")

from pathlib import Path
import re

backend_path = Path("backend/src/vibe_trading")

# 找到所有tools函数
tools_functions = {}
for py_file in backend_path.rglob("tools/*.py"):
    content = py_file.read_text()
    # 查找async def函数
    for match in re.finditer(r'async def (\w+)\(', content):
        func_name = match.group(1)
        if not func_name.startswith("_"):
            tools_functions[func_name] = py_file

console.print(f"  发现 {len(tools_functions)} 个tools函数")

# 检查它们是否被其他代码调用
unused_tools = []
used_tools = []

for func_name in tools_functions:
    # 在整个代码库中搜索函数调用
    found = False
    for py_file in backend_path.rglob("*.py"):
        if py_file.name.startswith("_") or py_file.name == "test_":
            continue
        content = py_file.read_text()
        if func_name in content:
            found = True
            break

    if found:
        used_tools.append(func_name)
    else:
        unused_tools.append(func_name)

console.print(f"  ✅ 被使用: {len(used_tools)} 个")
console.print(f"  [yellow]⚠️  未被使用: {len(unused_tools)} 个[/yellow]")

if unused_tools:
    console.print("\n  [dim]未使用的tools:[/dim]")
    for func in unused_tools[:10]:
        console.print(f"    - {func}")

checklist.append(("Tools使用率", f"{len(used_tools)}/{len(tools_functions)}"))

# =============================================================================
# 3. 检查各个Agent的数据获取方式
# =============================================================================
console.print("\n[bold cyan]3. 检查Agent数据获取方式[/bold cyan]")

# 检analysts
for role_file in backend_path.glob("agents/analysts/*.py"):
    if role_file.name == "base_analyst.py":
        continue
    content = role_file.read_text()

    role_name = role_file.stem
    has_tools = "tools=" in content
    uses_data_param = "context_data" in content or "market_data" in content

    if has_tools:
        console.print(f"  ✅ {role_name}: 使用tools")
    elif uses_data_param:
        console.print(f"  ⚠️  {role_name}: 数据通过prompt传递（非tools）")
    else:
        console.print(f"  [red]❌ {role_name}: 未知方式[/red]")

# =============================================================================
# 4. 总结
# =============================================================================
console.print("\n" + "=" * 60)
console.print("[bold]检查总结[/bold]")

table = Table(show_header=True)
table.add_column("检查项", style="cyan")
table.add_column("状态", style="green")
table.add_column("说明")

for item, status in checklist:
    if isinstance(status, bool):
        status_str = "✅ 通过" if status else "❌ 失败"
        style = "green" if status else "red"
    else:
        status_str = str(status)
        style = "yellow"

    table.add_row(item, f"[{style}]{status_str}[/{style}]", "")

console.print(table)

# 关键问题
console.print("\n[bold yellow]关键问题:[/bold yellow]")
console.print("1. Agent创建时tools字段为空")
console.print("2. 数据通过prompt硬编码传递，而非Agent按需调用")
console.print("3. 需要将tools函数包装成pi_agent框架格式")

console.print("\n[bold]建议:[/bold]")
console.print("当前架构下，coordinator负责调用tools获取数据")
console.print("数据通过prompt传递给Agent分析")
console.print("要改为Agent主动调用tools，需要：")
console.print("  - 将tools函数包装成pi_agent的Tool格式")
console.print("  - 在Agent创建时传入tools列表")
console.print("  - 修改Agent的prompt指导其如何使用tools")
console.print("=" * 60)

asyncio.run(check_agent_tools())
