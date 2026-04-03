"""
Token使用优化器

优化LLM Token使用，降低成本并提升效率。
"""
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict
import re

logger = logging.getLogger(__name__)


@dataclass
class TokenUsageStats:
    """Token使用统计"""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    request_count: int = 0

    # 成本估算（按1M tokens价格）
    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0
    total_cost_usd: float = 0.0

    # 效率指标
    avg_input_per_request: float = 0.0
    avg_output_per_request: float = 0.0

    def update(self, input_tokens: int, output_tokens: int, prices: Dict[str, float]):
        """更新统计"""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_tokens += input_tokens + output_tokens
        self.request_count += 1

        # 更新成本（示例价格，实际应该从配置读取）
        input_price = prices.get("input", 0.5)  # 每1M tokens价格
        output_price = prices.get("output", 1.5)

        self.input_cost_usd += (input_tokens / 1_000_000) * input_price
        self.output_cost_usd += (output_tokens / 1_000_000) * output_price
        self.total_cost_usd = self.input_cost_usd + self.output_cost_usd

        # 更新平均值
        self.avg_input_per_request = self.total_input_tokens / self.request_count
        self.avg_output_per_request = self.total_output_tokens / self.request_count


class TokenOptimizer:
    """
    Token优化器

    通过压缩Prompt、总结历史对话等方式优化Token使用。
    """

    def __init__(self):
        self.stats = TokenUsageStats()
        self.compression_ratios: Dict[str, float] = {}

    # Token价格（每1M tokens，美元）
    PRICE_PER_MILLION = {
        "gpt-4": {"input": 30.0, "output": 60.0},
        "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
        "claude-3-opus": {"input": 15.0, "output": 75.0},
        "claude-3-sonnet": {"input": 3.0, "output": 15.0},
        "glm-4": {"input": 1.0, "output": 2.0},
        "default": {"input": 0.5, "output": 1.5},
    }

    def compress_prompt(self, prompt: str, target_ratio: float = 0.7) -> str:
        """
        压缩Prompt

        Args:
            prompt: 原始Prompt
            target_ratio: 目标压缩比例（0.7表示压缩到70%）

        Returns:
            压缩后的Prompt
        """
        original_length = len(prompt)

        # 移除多余空白
        compressed = re.sub(r'\n\s*\n\s*\n', '\n\n', prompt)
        compressed = re.sub(r' +', ' ', compressed)

        # 移除冗余的格式标记
        compressed = re.sub(r'#+\s+', '#', compressed)
        compressed = re.sub(r'\*\*+', '*', compressed)

        # 压缩列表
        compressed = self._compress_lists(compressed)

        # 压缩重复结构
        compressed = self._compress_repeated_structures(compressed)

        compressed_length = len(compressed)
        ratio = compressed_length / original_length if original_length > 0 else 1.0

        self.compression_ratios["prompt"] = ratio

        logger.debug(
            f"Prompt compressed: {original_length} -> {compressed_length} "
            f"({ratio:.1%} of original)"
        )

        return compressed

    def _compress_lists(self, text: str) -> str:
        """压缩列表格式"""
        # 将多行列表转换为单行
        lines = text.split('\n')
        result = []
        in_list = False
        list_items = []

        for line in lines:
            stripped = line.strip()

            # 检测列表开始
            if re.match(r'^\d+\.\s+[-*•]', stripped):
                in_list = True
                # 提取列表项内容
                item = re.sub(r'^\d+\.\s+[-*•]\s*', '', stripped)
                list_items.append(item)
            elif in_list and stripped:
                # 列表结束
                if list_items:
                    result.append(f"• {', '.join(list_items[:5])}")
                    if len(list_items) > 5:
                        result.append(f"  ... and {len(list_items) - 5} more items")
                list_items = []
                in_list = False
                result.append(line)
            else:
                result.append(line)

        return '\n'.join(result)

    def _compress_repeated_structures(self, text: str) -> str:
        """压缩重复结构"""
        # 压缩重复的Agent报告格式
        # 例如：多个分析师的相似格式报告

        lines = text.split('\n')
        result = []
        skip_count = 0

        for i, line in enumerate(lines):
            # 检测重复的分隔线
            if re.match(r'^[=─]{20,}$', line):
                if skip_count > 0:
                    skip_count += 1
                    continue
                result.append(line)
                skip_count = 1
            else:
                skip_count = 0
                result.append(line)

        return '\n'.join(result)

    def summarize_history(
        self,
        messages: List[Dict],
        max_messages: int = 5,
        max_tokens_per_message: int = 500,
    ) -> str:
        """
        总结历史对话

        Args:
            messages: 历史消息列表
            max_messages: 保留的最大消息数
            max_tokens_per_message: 每条消息最大Token数

        Returns:
            总结后的对话历史
        """
        if not messages:
            return ""

        # 按时间排序，保留最近的消息
        sorted_messages = sorted(
            messages,
            key=lambda m: m.get('timestamp', ''),
            reverse=True
        )[:max_messages]

        summarized = []

        for msg in sorted_messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')

            # 截断过长的消息
            if len(content) > max_tokens_per_message:
                # 粗略估算Token（1 Token ≈ 4 字符）
                truncated = content[:max_tokens_per_message * 4]
                content = truncated + "... [truncated]"

            summarized.append(f"{role}: {content}")

        summary = "\n\n".join(summarized)

        logger.debug(
            f"History summarized: {len(messages)} -> {len(sorted_messages)} messages, "
            f"~{len(summary) / 4:.0f} tokens"
        )

        return summary

    def optimize_system_prompt(
        self,
        system_prompt: str,
        agent_role: str,
    ) -> str:
        """
        优化System Prompt

        Args:
            system_prompt: 原始System Prompt
            agent_role: Agent角色

        Returns:
            优化后的System Prompt
        """
        # 根据Agent角色使用预优化的Prompt模板
        optimized_prompts = {
            "technical_analyst": self._get_technical_analyst_prompt_template(),
            "fundamental_analyst": self._get_fundamental_analyst_prompt_template(),
            "bull_researcher": self._get_bull_researcher_prompt_template(),
            "bear_researcher": self._get_bear_researcher_prompt_template(),
            "trader": self._get_trader_prompt_template(),
            "portfolio_manager": self._get_portfolio_manager_prompt_template(),
        }

        template = optimized_prompts.get(agent_role)
        if template:
            return template

        # 没有预定义模板，使用通用优化
        return self._generic_prompt_optimization(system_prompt)

    def _get_technical_analyst_prompt_template(self) -> str:
        """技术分析师Prompt模板"""
        return """你是技术分析师。分析K线数据并给出建议。
核心指标：RSI、MACD、布林带、成交量。
输出格式：看涨/看跌/中性 + 简要理由。"""

    def _get_fundamental_analyst_prompt_template(self) -> str:
        """基本面分析师Prompt模板"""
        return """你是基本面分析师。分析链上数据和项目基本面。
关注指标：活跃地址、交易所流入流出、资金费率。
输出格式：看涨/看跌/中性 + 关键数据。"""

    def _get_bull_researcher_prompt_template(self) -> str:
        """看涨研究员Prompt模板"""
        return """你是看涨研究员。寻找做多机会，反驳看跌观点。
框架：技术30% + 基本面25% + 情绪20% + 宏观15% + 资金流10%。"""

    def _get_bear_researcher_prompt_template(self) -> str:
        """你是看跌研究员。寻找做空机会，反驳看涨观点。
框架：技术30% + 基本面25% + 情绪20% + 宏观15% + 风险10%。"""

    def _get_trader_prompt_template(self) -> str:
        """交易员Prompt模板"""
        return """你是交易员。根据已确定方向制定执行方案。
不判断是否进场，专注如何进场。
输出：订单类型、分批计划、止损止盈。"""

    def _get_portfolio_manager_prompt_template(self) -> str:
        """投资组合经理Prompt模板"""
        return """你是投资组合经理。最终决策审批。
综合各方意见，给出最终决定。"""

    def _generic_prompt_optimization(self, prompt: str) -> str:
        """通用Prompt优化"""
        # 移除冗余内容
        optimized = prompt

        # 移除重复的指令
        lines = optimized.split('\n')
        seen = set()
        result = []

        for line in lines:
            stripped = line.strip().lower()
            if stripped and stripped not in seen:
                seen.add(stripped)
                result.append(line)

        return '\n'.join(result)

    def estimate_tokens(self, text: str) -> int:
        """
        估算Token数量

        Args:
            text: 输入文本

        Returns:
            估算的Token数量
        """
        # 粗略估算：英文 ≈ 4字符/token，中文 ≈ 2字符/token
        # 混合文本取中间值
        char_count = len(text)
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_chars = char_count - chinese_chars

        estimated_tokens = (chinese_chars / 2) + (english_chars / 4)

        return int(estimated_tokens)

    def track_usage(
        self,
        agent_name: str,
        input_text: str,
        output_text: str,
        model: str = "default",
    ):
        """
        跟踪Token使用

        Args:
            agent_name: Agent名称
            input_text: 输入文本
            output_text: 输出文本
            model: 模型名称
        """
        input_tokens = self.estimate_tokens(input_text)
        output_tokens = self.estimate_tokens(output_text)

        prices = self.PRICE_PER_MILLION.get(model, self.PRICE_PER_MILLION["default"])

        self.stats.update(input_tokens, output_tokens, prices)

        logger.debug(
            f"Token usage for {agent_name}: "
            f"input={input_tokens}, output={output_tokens}, "
            f"cost=${self.stats.total_cost_usd:.4f}"
        )

    def get_optimization_suggestions(self) -> List[str]:
        """
        获取优化建议

        Returns:
            优化建议列表
        """
        suggestions = []

        # 基于统计数据的建议
        if self.stats.avg_input_per_request > 2000:
            suggestions.append(
                "⚠️ 平均输入Token过高(>2000)，考虑压缩Prompt或总结历史"
            )

        if self.stats.avg_output_per_request > 1000:
            suggestions.append(
                "⚠️ 平均输出Token过高(>1000)，考虑限制输出长度或总结响应"
            )

        if self.stats.request_count > 0:
            cost_per_request = self.stats.total_cost_usd / self.stats.request_count
            if cost_per_request > 0.01:  # 每次请求超过1美分
                suggestions.append(
                    f"⚠️ 每次请求成本${cost_per_request:.4f}较高，考虑优化"
                )

        # 检查压缩效率
        if "prompt" in self.compression_ratios:
            ratio = self.compression_ratios["prompt"]
            if ratio > 0.8:
                suggestions.append(
                    f"⚠️ Prompt压缩比例{ratio:.1%}偏高，可以进一步压缩"
                )

        if not suggestions:
            suggestions.append("✅ Token使用效率良好")

        return suggestions

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "total_input_tokens": self.stats.total_input_tokens,
            "total_output_tokens": self.stats.total_output_tokens,
            "total_tokens": self.stats.total_tokens,
            "request_count": self.stats.request_count,
            "total_cost_usd": round(self.stats.total_cost_usd, 4),
            "avg_input_per_request": round(self.stats.avg_input_per_request, 1),
            "avg_output_per_request": round(self.stats.avg_output_per_request, 1),
            "compression_ratios": self.compression_ratios,
        }


class PromptTemplateManager:
    """
    Prompt模板管理器

    管理和复用Prompt模板。
    """

    def __init__(self):
        self.templates: Dict[str, str] = {}

    def register_template(self, name: str, template: str):
        """注册模板"""
        self.templates[name] = template

    def get_template(self, name: str) -> Optional[str]:
        """获取模板"""
        return self.templates.get(name)

    def render_template(
        self,
        name: str,
        **kwargs
    ) -> str:
        """
        渲染模板

        Args:
            name: 模板名称
            **kwargs: 模板变量

        Returns:
            渲染后的字符串
        """
        template = self.get_template(name)
        if template is None:
            return ""

        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing template variable: {e}")
            return template


# 全局单例
_token_optimizer: Optional[TokenOptimizer] = None
_template_manager: Optional[PromptTemplateManager] = None


def get_token_optimizer() -> TokenOptimizer:
    """获取全局Token优化器"""
    global _token_optimizer
    if _token_optimizer is None:
        _token_optimizer = TokenOptimizer()
    return _token_optimizer


def get_template_manager() -> PromptTemplateManager:
    """获取全局模板管理器"""
    global _template_manager
    if _template_manager is None:
        _template_manager = PromptTemplateManager()
        return _template_manager


# 装饰器
def track_tokens(agent_name: str, model: str = "default"):
    """
    Token追踪装饰器

    使用示例:
        @track_tokens("TechnicalAnalyst", "gpt-4")
        async def analyze(context):
            prompt = "..."
            response = await llm.generate(prompt)
            return response
    """
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            optimizer = get_token_optimizer()

            # 获取输入（通常是第一个参数或context中的prompt）
            input_text = ""
            if args and isinstance(args[0], str):
                input_text = args[0]
            elif 'prompt' in kwargs:
                input_text = kwargs['prompt']
            elif 'context' in kwargs:
                input_text = str(kwargs['context'])

            # 执行函数
            output = await func(*args, **kwargs)

            # 追踪使用
            output_text = str(output)
            optimizer.track_usage(agent_name, input_text, output_text, model)

            return output

        return wrapper


# 使用示例
async def example_usage():
    """使用示例"""

    optimizer = get_token_optimizer()

    # 测试压缩
    long_prompt = """
    # 技术分析报告

    ## 市场概况
    - 当前价格: $50,000
    - 24小时变化: +5.2%
    - 成交量: 1.2M BTC

    ## 技术指标
    ### RSI
    - 当前值: 58
    - 状态: 中性偏多

    ### MACD
    - 当前值: 金叉
    - 信号: 看涨

    ### 布林带
    - 上轨: $51,000
    - 中轨: $50,000
    - 下轨: $49,000
    """ * 3

    compressed = optimizer.compress_prompt(long_prompt)
    print(f"Original: {len(long_prompt)} chars")
    print(f"Compressed: {len(compressed)} chars")

    # 测试历史总结
    messages = [
        {"role": "user", "content": "Analyze BTC", "timestamp": "2024-01-01T10:00:00"},
        {"role": "assistant", "content": "BTC is bullish", "timestamp": "2024-01-01T10:01:00"},
        {"role": "user", "content": "What about ETH?", "timestamp": "2024-01-01T10:02:00"},
        {"role": "assistant", "content": "ETH is neutral", "timestamp": "2024-01-01T10:03:00"},
    ]

    summary = optimizer.summarize_history(messages)
    print(f"\nHistory summary:\n{summary}")

    # 获取优化建议
    suggestions = optimizer.get_optimization_suggestions()
    print(f"\nOptimization suggestions:")
    for suggestion in suggestions:
        print(f"  {suggestion}")


if __name__ == "__main__":
    asyncio.run(example_usage())
