"""
决策流程可视化

生成决策流程的可视化图表。
"""
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class OutputFormat(str, Enum):
    """输出格式"""
    MERMAID = "mermaid"
    PLANTUML = "plantuml"
    ASCII = "ascii"
    JSON = "json"


@dataclass
class DecisionNode:
    """决策节点"""
    node_id: str
    label: str
    node_type: str  # start, process, decision, end, connector
    phase: Optional[int] = None
    agent_name: Optional[str] = None
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class DecisionEdge:
    """决策边（连接）"""
    from_node: str
    to_node: str
    label: str
    condition: Optional[str] = None
    style: str = "solid"  # solid, dashed


class DecisionTreeVisualizer:
    """
    决策树可视化器

    生成决策流程的多种可视化格式。
    """

    def __init__(self):
        self.nodes: List[DecisionNode] = []
        self.edges: List[DecisionEdge] = []

    def add_node(
        self,
        node_id: str,
        label: str,
        node_type: str,
        phase: Optional[int] = None,
        agent_name: Optional[str] = None,
        **metadata
    ):
        """添加节点"""
        node = DecisionNode(
            node_id=node_id,
            label=label,
            node_type=node_type,
            phase=phase,
            agent_name=agent_name,
            metadata=metadata
        )
        self.nodes.append(node)

    def add_edge(
        self,
        from_node: str,
        to_node: str,
        label: str = "",
        condition: Optional[str] = None,
        style: str = "solid"
    ):
        """添加边"""
        edge = DecisionEdge(
            from_node=from_node,
            to_node=to_node,
            label=label,
            condition=condition,
            style=style
        )
        self.edges.append(edge)

    def generate_mermaid(self) -> str:
        """生成Mermaid格式流程图"""
        lines = ["graph TB"]

        # 添加节点
        for node in self.nodes:
            # 根据类型选择形状
            shape = self._get_mermaid_shape(node.node_type)
            lines.append(f"    {node.node_id}[{node.label}]{shape}")

        # 添加边
        for edge in self.edges:
            if edge.condition:
                label = f"{edge.label}|{edge.condition}"
            else:
                label = edge.label

            style = ":" + edge.style if edge.style != "solid" else ""

            lines.append(f"    {edge.from_node} -->|{label}|{edge.to_node}{style}")

        # 添加样式
        lines.extend(self._get_mermaid_styles())

        return "\n".join(lines)

    def generate_plantuml(self) -> str:
        """生成PlantUML格式流程图"""
        lines = ["@startuml", "skinparam activity {", "  BackgroundColor #F3F3F3", "}", ""]
        lines.append("start")

        # 添加节点
        for node in self.nodes:
            if node.node_type == "start":
                lines.append(f":{node.label};")
            elif node.node_type == "end":
                lines.append(f"stop")
                lines.append(f":{node.label};")
            elif node.node_type == "decision":
                lines.append(f"if {node.label}? then")
            elif node.node_type == "process":
                lines.append(f":{node.label};")
            elif node.node_type == "connector":
                lines.append(f":{node.label};")

        lines.append("@enduml")
        return "\n".join(lines)

    def generate_ascii(self) -> str:
        """生成ASCII艺术流程图"""
        lines = []
        lines.append("┌" + "─" * 50 + "┐")

        # 根据节点类型生成不同形状
        for i, node in enumerate(self.nodes):
            if node.node_type == "start":
                lines.append(f"│ 🔵 {node.label:^44} │")
            elif node.node_type == "end":
                lines.append(f"│ 🏁 {node.label:^44} │")
            elif node.node_type == "decision":
                lines.append(f"│ ◻️ {node.label:^44} │")
            elif node.node_type == "process":
                lines.append(f"│ ⚙️ {node.label:^44} │")
            else:
                lines.append(f"│ • {node.label:^46} │")

            # 添加连接
            if i < len(self.nodes) - 1:
                lines.append("│" + " " * 50 + "│")

        lines.append("└" + "─" * 50 + "┘")
        return "\n".join(lines)

    def generate_json(self) -> Dict:
        """生成JSON格式"""
        return {
            "nodes": [
                {
                    "id": n.node_id,
                    "label": n.label,
                    "type": n.node_type,
                    "phase": n.phase,
                    "agent": n.agent_name,
                    "metadata": n.metadata,
                }
                for n in self.nodes
            ],
            "edges": [
                {
                    "from": e.from_node,
                    "to": e.to_node,
                    "label": e.label,
                    "condition": e.condition,
                    "style": e.style,
                }
                for e in self.edges
            ]
        }

    def _get_mermaid_shape(self, node_type: str) -> str:
        """获取Mermaid形状"""
        shapes = {
            "start": "([{}])",
            "end": "([{}])",
            "process": "[{}]",
            "decision": "{{{}}}",
            "connector": "(({}))",
        }
        return shapes.get(node_type, "[{}]")

    def _get_mermaid_styles(self) -> List[str]:
        """获取Mermaid样式"""
        return [
            "    classDef phase1 fill:#4299e1,stroke:#2b6cb0,stroke-width:2px",
            "    classDef phase2 fill:#9f7aea,stroke:#6b46c1,stroke-width:2px",
            "    classDef phase3 fill:#ed8936,stroke:#c05621,stroke-width:2px",
            "    classDef phase4 fill:#38b2ac,stroke:#2c7a7b,stroke-width:2px",
            "    classDef startend fill:#48bb78,stroke:#2f855a,stroke-width:2px",
            "",
            "    class phase1_node phase1",
            "    class phase2_node phase2",
            "    class phase3_node phase3",
            "    class phase4_node phase4",
        ]


class DecisionFlowBuilder:
    """
    决策流程构建器

    方便构建决策流程的工具类。
    """

    def __init__(self):
        self.visualizer = DecisionTreeVisualizer()
        self.node_counter = 0
        self.phase_counter = 0

    def _get_next_node_id(self) -> str:
        """生成下一个节点ID"""
        self.node_counter += 1
        return f"node_{self.node_counter}"

    def add_start(self, label: str = "开始") -> str:
        """添加开始节点"""
        node_id = self._get_next_node_id()
        self.visualizer.add_node(
            node_id=node_id,
            label=label,
            node_type="start"
        )
        return node_id

    def add_phase(self, phase_num: int, name: str, agents: List[str]) -> str:
        """添加阶段节点"""
        self.phase_counter = phase_num
        node_id = self._get_next_node_id()

        agent_list = ", ".join(agents)
        label = f"Phase {phase_num}: {name}\n({agent_list})"

        self.visualizer.add_node(
            node_id=node_id,
            label=label,
            node_type="process",
            phase=phase_num
        )

        return node_id

    def add_decision(self, label: str, yes_action: str, no_action: str) -> Tuple[str, str, str]:
        """添加决策节点"""
        decision_id = self._get_next_node_id()
        yes_id = self._get_next_node_id()
        no_id = self._get_next_node_id()

        # 决策节点
        self.visualizer.add_node(
            node_id=decision_id,
            label=label,
            node_type="decision"
        )

        # Yes分支
        self.visualizer.add_node(
            node_id=yes_id,
            label=yes_action,
            node_type="process"
        )
        self.visualizer.add_edge(
            from_node=decision_id,
            to_node=yes_id,
            label="",
            condition="Yes"
        )

        # No分支
        self.visualizer.add_node(
            node_id=no_id,
            label=no_action,
            node_type="process"
        )
        self.visualizer.add_edge(
            from_node=decision_id,
            to_node=no_id,
            label="",
            condition="No"
        )

        return decision_id, yes_id, no_id

    def add_end(self, label: str = "结束") -> str:
        """添加结束节点"""
        node_id = self._get_next_node_id()
        self.visualizer.add_node(
            node_id=node_id,
            label=label,
            node_type="end"
        )
        return node_id

    def add_connector(self, from_node: str, to_node: str, label: str = ""):
        """添加连接"""
        self.visualizer.add_edge(
            from_node=from_node,
            to_node=to_node,
            label=label
        )

    def build_standard_flow(self) -> DecisionTreeVisualizer:
        """构建标准决策流程"""
        # 开始
        start = self.add_start("新K线到达")

        # Phase 1
        phase1 = self.add_phase(1, "分析师团队", ["技术", "基本面", "新闻", "情绪"])
        self.add_connector(start, phase1)

        # Phase 2
        phase2 = self.add_phase(2, "研究员团队", ["看涨", "看跌", "裁决"])
        self.add_connector(phase1, phase2)

        # Phase 3
        phase3 = self.add_phase(3, "风控团队", ["激进", "中立", "保守"])
        self.add_connector(phase2, phase3)

        # Phase 4
        phase4 = self.add_phase(4, "决策层", ["交易员", "投组经理"])
        self.add_connector(phase3, phase4)

        # 决策
        decision, yes, no = self.add_decision(
            "是否交易?",
            "执行交易",
            "观望"
        )
        self.add_connector(phase4, decision)

        # 结束
        end_yes = self.add_end("交易执行")
        end_no = self.add_end("观望")
        self.add_connector(yes, end_yes)
        self.add_connector(no, end_no)

        return self.visualizer

    def get_visualizer(self) -> DecisionTreeVisualizer:
        """获取可视化器"""
        return self.visualizer


def visualize_decision_history(
    decision_history: List[Dict],
    format: OutputFormat = OutputFormat.MERMAID
) -> str:
    """
    可视化决策历史

    Args:
        decision_history: 决策历史列表
        format: 输出格式

    Returns:
        可视化字符串
    """
    visualizer = DecisionTreeVisualizer()
    builder = DecisionFlowBuilder()

    # 构建标准流程
    builder.visualizer = visualizer
    builder.build_standard_flow()

    # 根据格式返回
    if format == OutputFormat.MERMAID:
        return visualizer.generate_mermaid()
    elif format == OutputFormat.PLANTUML:
        return visualizer.generate_plantuml()
    elif format == OutputFormat.ASCII:
        return visualizer.generate_ascii()
    elif format == OutputFormat.JSON:
        import json
        return json.dumps(visualizer.generate_json(), indent=2)
    else:
        return visualizer.generate_mermaid()


# 使用示例
def example_usage():
    """使用示例"""

    # 方式1: 使用构建器
    builder = DecisionFlowBuilder()
    visualizer = builder.build_standard_flow()

    print("=" * 60)
    print("Mermaid Format:")
    print("=" * 60)
    print(visualizer.generate_mermaid())

    print("\n" + "=" * 60)
    print("ASCII Format:")
    print("=" * 60)
    print(visualizer.generate_ascii())

    # 方式2: 直接使用可视化器
    viz = DecisionTreeVisualizer()
    viz.add_node("start", "开始", "start")
    viz.add_node("p1", "Phase 1", "process", phase=1)
    viz.add_edge("start", "p1", "开始分析")

    print("\n" + "=" * 60)
    print("JSON Format:")
    print("=" * 60)
    import json
    print(json.dumps(viz.generate_json(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    example_usage()
