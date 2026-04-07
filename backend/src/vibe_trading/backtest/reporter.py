"""
回测报告生成器

生成文本、HTML和JSON格式的回测报告。
"""
from __future__ import annotations

from typing import Dict, List

from pi_logger import get_logger

from vibe_trading.backtest.models import (
    BacktestResult,
    ReportFormat,
)

logger = get_logger(__name__)


class BacktestReporter:
    """
    回测报告生成器

    支持多种报告格式：
    - TEXT: Rich格式化的终端输出
    - HTML: Plotly交互式图表 + Jinja2模板
    - JSON: 机器可读的结构化数据
    """

    async def generate_reports(
        self,
        result: BacktestResult,
        formats: List[ReportFormat],
    ) -> Dict[ReportFormat, str]:
        """
        生成多格式报告

        Args:
            result: 回测结果
            formats: 报告格式列表

        Returns:
            Dict[ReportFormat, str]: 格式到报告内容的映射
        """
        reports = {}

        for format_type in formats:
            try:
                if format_type == ReportFormat.TEXT:
                    reports[format_type] = self._generate_text_report(result)
                elif format_type == ReportFormat.HTML:
                    reports[format_type] = await self._generate_html_report(result)
                elif format_type == ReportFormat.JSON:
                    reports[format_type] = self._generate_json_report(result)
            except Exception as e:
                logger.error(f"生成{format_type.value}报告失败: {e}", exc_info=True)

        return reports

    def _generate_text_report(self, result: BacktestResult) -> str:
        """生成文本报告"""
        lines = []
        lines.append("=" * 70)
        lines.append("回测报告".center(70))
        lines.append("=" * 70)
        lines.append("")

        # 基本信息
        lines.append("【基本信息】")
        lines.append(f"  交易品种: {result.config.symbol}")
        lines.append(f"  K线间隔: {result.config.interval}")
        lines.append(f"  回测时间: {result.config.start_time.strftime('%Y-%m-%d')} ~ {result.config.end_time.strftime('%Y-%m-%d')}")
        lines.append(f"  LLM模式: {result.config.llm_mode.value}")
        lines.append(f"  初始余额: ${result.config.initial_balance:,.2f}")
        lines.append("")

        if result.error_message:
            lines.append("【错误】")
            lines.append(f"  {result.error_message}")
            return "\n".join(lines)

        if result.metrics is None:
            lines.append("【状态】回测失败，无指标数据")
            return "\n".join(lines)

        # 收益指标
        lines.append("【收益指标】")
        lines.append(f"  总收益率: {result.metrics.total_return:.2%}")
        lines.append(f"  总盈亏: ${result.config.initial_balance * result.metrics.total_return:,.2f}")
        lines.append(f"  平均每笔: ${result.metrics.avg_trade_pnl:.2f}")
        lines.append(f"  盈利交易平均: ${result.metrics.avg_win_pnl:.2f}")
        lines.append(f"  亏损交易平均: ${result.metrics.avg_loss_pnl:.2f}")
        lines.append("")

        # 风险指标
        lines.append("【风险指标】")
        lines.append(f"  夏普比率: {result.metrics.sharpe_ratio:.2f}")
        lines.append(f"  Sortino比率: {result.metrics.sortino_ratio:.2f}")
        lines.append(f"  最大回撤: {result.metrics.max_drawdown:.2%}")
        lines.append(f"  VaR (95%): ${result.metrics.var_95:.2f}")
        lines.append(f"  VaR (99%): ${result.metrics.var_99:.2f}")
        lines.append(f"  最大连续亏损: {result.metrics.max_consecutive_losses} 次")
        lines.append("")

        # 交易统计
        lines.append("【交易统计】")
        lines.append(f"  总交易数: {result.metrics.total_trades}")
        lines.append(f"  盈利交易: {result.metrics.profitable_trades}")
        lines.append(f"  亏损交易: {result.metrics.losing_trades}")
        lines.append(f"  胜率: {result.metrics.win_rate:.2%}")
        lines.append(f"  盈亏比: {result.metrics.profit_factor:.2f}")
        lines.append(f"  平均持仓时长: {result.metrics.avg_hold_duration_hours:.2f} 小时")
        lines.append("")

        # Agent表现
        if result.metrics.agent_rankings:
            lines.append("【Agent表现排名】")
            for i, (agent_name, accuracy) in enumerate(result.metrics.agent_rankings[:10], 1):
                agent_perf = result.metrics.agent_performances.get(agent_name)
                if agent_perf:
                    lines.append(
                        f"  {i:2d}. {agent_name}: "
                        f"准确率 {accuracy:.2%} "
                        f"({agent_perf.correct_predictions}/{agent_perf.total_decisions})"
                    )
            lines.append("")

        # 执行信息
        lines.append("【执行信息】")
        lines.append(f"  总K线数: {result.total_klines}")
        lines.append(f"  总决策数: {len(result.decisions)}")
        lines.append(f"  执行交易数: {len(result.trades)}")
        lines.append(f"  LLM调用数: {result.llm_calls}")
        lines.append(f"  缓存命中数: {result.llm_cache_hits}")
        lines.append(f"  缓存命中率: {result.cache_hit_rate:.2%}")
        lines.append(f"  执行时间: {result.execution_time:.2f} 秒")
        lines.append("")

        lines.append("=" * 70)
        lines.append(f"报告生成时间: {result.completed_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 70)

        return "\n".join(lines)

    async def _generate_html_report(self, result: BacktestResult) -> str:
        """生成HTML报告"""
        # HTML模板
        html_template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>回测报告 - {symbol}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            text-align: center;
            margin-bottom: 30px;
        }}
        .section {{
            margin-bottom: 30px;
        }}
        .section h2 {{
            color: #555;
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 10px;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        .metric-card {{
            background-color: #f9f9f9;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #4CAF50;
        }}
        .metric-label {{
            font-size: 14px;
            color: #666;
            margin-bottom: 5px;
        }}
        .metric-value {{
            font-size: 24px;
            font-weight: bold;
            color: #333;
        }}
        .metric-value.positive {{
            color: #4CAF50;
        }}
        .metric-value.negative {{
            color: #f44336;
        }}
        .chart {{
            margin-bottom: 30px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #4CAF50;
            color: white;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .footer {{
            text-align: center;
            color: #999;
            margin-top: 30px;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 回测报告 - {symbol}</h1>

        <div class="section">
            <h2>基本信息</h2>
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-label">交易品种</div>
                    <div class="metric-value">{symbol}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">K线间隔</div>
                    <div class="metric-value">{interval}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">回测时间</div>
                    <div class="metric-value">{start_date} ~ {end_date}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">LLM模式</div>
                    <div class="metric-value">{llm_mode}</div>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>收益指标</h2>
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-label">总收益率</div>
                    <div class="metric-value {return_class}">{total_return:.2%}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">总盈亏</div>
                    <div class="metric-value {pnl_class}">${total_pnl:,.2f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">夏普比率</div>
                    <div class="metric-value">{sharpe:.2f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">最大回撤</div>
                    <div class="metric-value negative">{max_drawdown:.2%}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">胜率</div>
                    <div class="metric-value">{win_rate:.2%}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">盈亏比</div>
                    <div class="metric-value">{profit_factor:.2f}</div>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>资金曲线</h2>
            <div id="equity-chart" class="chart"></div>
        </div>

        <div class="section">
            <h2>回撤曲线</h2>
            <div id="drawdown-chart" class="chart"></div>
        </div>

        {agent_ranking_section}

        <div class="section">
            <h2>交易明细</h2>
            <table>
                <thead>
                    <tr>
                        <th>交易ID</th>
                        <th>入场时间</th>
                        <th>出场时间</th>
                        <th>方向</th>
                        <th>入场价</th>
                        <th>出场价</th>
                        <th>盈亏</th>
                        <th>盈亏率</th>
                    </tr>
                </thead>
                <tbody>
                    {trade_rows}
                </tbody>
            </table>
        </div>

        <div class="footer">
            <p>报告生成时间: {generation_time}</p>
            <p>执行时间: {execution_time:.2f} 秒 | K线数: {total_klines} | LLM调用: {llm_calls}</p>
        </div>
    </div>

    <script>
        // 资金曲线图
        const equityTrace = {{
            x: {timestamps},
            y: {equity_curve},
            type: 'scatter',
            mode: 'lines',
            name: '权益',
            line: {{color: '#4CAF50'}}
        }};

        const equityLayout = {{
            title: '资金曲线',
            xaxis: {{title: '时间'}},
            yaxis: {{title: '权益 (USDT)'}},
            hovermode: 'closest'
        }};

        Plotly.newPlot('equity-chart', [equityTrace], equityLayout);

        // 回撤曲线图
        const drawdownTrace = {{
            x: {timestamps},
            y: {drawdown_curve},
            type: 'scatter',
            mode: 'lines',
            name: '回撤',
            line: {{color: '#f44336'}}
        }};

        const drawdownLayout = {{
            title: '回撤曲线',
            xaxis: {{title: '时间'}},
            yaxis: {{title: '回撤 (%)'}},
            hovermode: 'closest'
        }};

        Plotly.newPlot('drawdown-chart', [drawdownTrace], drawdownLayout);
    </script>
</body>
</html>
"""

        # 准备数据
        metrics = result.metrics

        # 确定数值样式
        return_class = "positive" if metrics.total_return >= 0 else "negative"
        pnl_class = "positive" if (metrics.total_return * result.config.initial_balance) >= 0 else "negative"

        # Agent排名表格
        agent_ranking_rows = ""
        if metrics.agent_rankings:
            agent_ranking_rows = '<div class="section">\n<h2>Agent表现排名</h2>\n<table>\n<thead>\n<tr>\n<th>排名</th>\n<th>Agent</th>\n<th>准确率</th>\n<th>正确次数</th>\n<th>总次数</th>\n</tr>\n</thead>\n<tbody>'
            for i, (agent_name, accuracy) in enumerate(metrics.agent_rankings[:10], 1):
                agent_perf = metrics.agent_performances.get(agent_name)
                if agent_perf:
                    agent_ranking_rows += f'<tr>\n<td>{i}</td>\n<td>{agent_name}</td>\n<td>{accuracy:.2%}</td>\n<td>{agent_perf.correct_predictions}</td>\n<td>{agent_perf.total_decisions}</td>\n</tr>'
            agent_ranking_rows += '</tbody>\n</table>\n</div>'

        # 交易明细行
        trade_rows = ""
        for trade in result.trades[:50]:  # 最多显示50笔
            pnl_class = "positive" if (trade.pnl or 0) >= 0 else "negative"
            trade_rows += f"""<tr>
                <td>{trade.trade_id[:8]}...</td>
                <td>{trade.entry_time.strftime('%Y-%m-%d %H:%M') if trade.entry_time else '-'}</td>
                <td>{trade.exit_time.strftime('%Y-%m-%d %H:%M') if trade.exit_time else '-'}</td>
                <td>{trade.side}</td>
                <td>${trade.entry_price:.2f}</td>
                <td>${trade.exit_price:.2f if trade.exit_price else 0:.2f}</td>
                <td class="{pnl_class}">${trade.pnl:.2f if trade.pnl else 0:.2f}</td>
                <td class="{pnl_class}">{f"{trade.pnl_percentage:.2f}%" if trade.pnl_percentage else "0.00%"}</td>
            </tr>"""

        # 时间戳列表
        timestamps = [t.isoformat() for t in metrics.timestamps] if metrics.timestamps else []
        equity_curve = metrics.equity_curve if metrics.equity_curve else []
        drawdown_curve = [d * 100 for d in metrics.drawdown_curve] if metrics.drawdown_curve else []

        # 渲染模板
        return html_template.format(
            symbol=result.config.symbol,
            interval=result.config.interval,
            start_date=result.config.start_time.strftime('%Y-%m-%d'),
            end_date=result.config.end_time.strftime('%Y-%m-%d'),
            llm_mode=result.config.llm_mode.value,
            return_class=return_class,
            total_return=metrics.total_return,
            pnl_class=pnl_class,
            total_pnl=metrics.total_return * result.config.initial_balance,
            sharpe=metrics.sharpe_ratio,
            max_drawdown=metrics.max_drawdown,
            win_rate=metrics.win_rate,
            profit_factor=metrics.profit_factor,
            timestamps=timestamps,
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve,
            agent_ranking_section=agent_ranking_rows,
            trade_rows=trade_rows,
            generation_time=result.completed_at.strftime('%Y-%m-%d %H:%M:%S'),
            execution_time=result.execution_time,
            total_klines=result.total_klines,
            llm_calls=result.llm_calls,
        )

    def _generate_json_report(self, result: BacktestResult) -> str:
        """生成JSON报告"""
        import json

        data = {
            "config": {
                "symbol": result.config.symbol,
                "interval": result.config.interval,
                "start_time": result.config.start_time.isoformat(),
                "end_time": result.config.end_time.isoformat(),
                "initial_balance": result.config.initial_balance,
                "llm_mode": result.config.llm_mode.value,
                "prompt_id": result.config.prompt_id,
                "prompt_version": result.config.prompt_version,
            },
            "metrics": None if result.metrics is None else {
                "total_return": result.metrics.total_return,
                "win_rate": result.metrics.win_rate,
                "sharpe_ratio": result.metrics.sharpe_ratio,
                "sortino_ratio": result.metrics.sortino_ratio,
                "max_drawdown": result.metrics.max_drawdown,
                "profit_factor": result.metrics.profit_factor,
                "avg_trade_pnl": result.metrics.avg_trade_pnl,
                "avg_win_pnl": result.metrics.avg_win_pnl,
                "avg_loss_pnl": result.metrics.avg_loss_pnl,
                "total_trades": result.metrics.total_trades,
                "profitable_trades": result.metrics.profitable_trades,
                "losing_trades": result.metrics.losing_trades,
                "var_95": result.metrics.var_95,
                "var_99": result.metrics.var_99,
                "expected_shortfall_95": result.metrics.expected_shortfall_95,
                "max_consecutive_losses": result.metrics.max_consecutive_losses,
                "avg_hold_duration_hours": result.metrics.avg_hold_duration_hours,
                "equity_curve": result.metrics.equity_curve,
                "drawdown_curve": result.metrics.drawdown_curve,
                "agent_performances": {
                    name: {
                        "total_decisions": perf.total_decisions,
                        "correct_predictions": perf.correct_predictions,
                        "accuracy": perf.accuracy,
                    }
                    for name, perf in result.metrics.agent_performances.items()
                },
                "agent_rankings": result.metrics.agent_rankings,
            },
            "trades": [
                {
                    "trade_id": t.trade_id,
                    "symbol": t.symbol,
                    "entry_time": t.entry_time.isoformat() if t.entry_time else None,
                    "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "quantity": t.quantity,
                    "side": t.side,
                    "pnl": t.pnl,
                    "pnl_percentage": t.pnl_percentage,
                    "decision_id": t.decision_id,
                    "signal": t.signal.value,
                    "confidence": t.confidence,
                    "market_condition": t.market_condition,
                    "agent_contributions": t.agent_contributions,
                    "hold_duration_hours": t.hold_duration_hours,
                }
                for t in result.trades
            ],
            "decisions": [
                {
                    "decision_id": d.decision_id,
                    "timestamp": d.timestamp.isoformat(),
                    "current_price": d.current_price,
                    "signal": d.signal.value,
                    "confidence": d.confidence,
                    "strength": d.strength,
                    "executed": d.executed,
                    "trade_id": d.trade_id,
                }
                for d in result.decisions
            ],
            "execution": {
                "total_klines": result.total_klines,
                "llm_calls": result.llm_calls,
                "llm_cache_hits": result.llm_cache_hits,
                "cache_hit_rate": result.cache_hit_rate,
                "execution_time": result.execution_time,
                "started_at": result.started_at.isoformat(),
                "completed_at": result.completed_at.isoformat(),
            },
            "error_message": result.error_message,
        }

        return json.dumps(data, indent=2, ensure_ascii=False)


# ============================================================================
# 便捷函数
# ============================================================================

async def generate_backtest_report(
    result: BacktestResult,
    format: ReportFormat = ReportFormat.TEXT,
) -> str:
    """
    便捷函数：生成回测报告

    Args:
        result: 回测结果
        format: 报告格式

    Returns:
        报告内容
    """
    reporter = BacktestReporter()
    reports = await reporter.generate_reports(result, [format])
    return reports.get(format, "")
