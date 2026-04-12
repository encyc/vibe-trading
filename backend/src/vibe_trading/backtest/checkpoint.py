"""
检查点管理器

支持回测进度的保存和恢复。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pi_logger import get_logger

from vibe_trading.backtest.models import BacktestConfig
from vibe_trading.backtest.executor import ExecutionState

logger = get_logger(__name__)


@dataclass
class BacktestCheckpoint:
    """回测检查点"""
    checkpoint_id: str  # 唯一标识
    config: BacktestConfig  # 回测配置
    current_kline_index: int  # 当前K线索引
    execution_state: Dict[str, Any]  # 执行状态（序列化的ExecutionState）
    coordinator_state: Optional[Dict[str, Any]] = None  # 协调器状态（可选）
    created_at: datetime = None  # 创建时间

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class CheckpointManager:
    """
    检查点管理器

    负责保存和加载回测检查点。
    """

    def __init__(self, checkpoint_dir: str = "./checkpoints"):
        """
        初始化检查点管理器

        Args:
            checkpoint_dir: 检查点保存目录
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"CheckpointManager initialized with dir: {self.checkpoint_dir}")

    def _get_checkpoint_path(self, checkpoint_id: str) -> Path:
        """获取检查点文件路径"""
        return self.checkpoint_dir / f"{checkpoint_id}.json"

    def _serialize_execution_state(self, state: ExecutionState) -> Dict[str, Any]:
        """
        序列化执行状态

        Args:
            state: ExecutionState对象

        Returns:
            序列化后的字典
        """
        return {
            "current_balance": state.current_balance,
            "current_positions": {
                symbol: {
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "quantity": pos.quantity,
                    "entry_price": pos.entry_price,
                    "unrealized_pnl": pos.unrealized_pnl,
                }
                for symbol, pos in state.current_positions.items()
            },
            "open_trades": {
                trade_id: {
                    "trade_id": trade.trade_id,
                    "symbol": trade.symbol,
                    "entry_time": trade.entry_time.isoformat(),
                    "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
                    "entry_price": trade.entry_price,
                    "exit_price": trade.exit_price,
                    "quantity": trade.quantity,
                    "side": trade.side,
                    "pnl": trade.pnl,
                    "pnl_percentage": trade.pnl_percentage,
                    "decision_id": trade.decision_id,
                    "signal": trade.signal.value,
                    "confidence": trade.confidence,
                    "market_condition": trade.market_condition,
                    "agent_contributions": trade.agent_contributions,
                    "hold_duration_hours": trade.hold_duration_hours,
                }
                for trade_id, trade in state.open_trades.items()
            },
            "decision_history": [
                {
                    "decision_id": d.decision_id,
                    "timestamp": d.timestamp.isoformat(),
                    "signal": d.signal.value,
                    "confidence": d.confidence,
                    "executed": d.executed,
                    "trade_id": d.trade_id,
                }
                for d in state.decision_history
            ],
            "trade_history": [
                {
                    "trade_id": t.trade_id,
                    "symbol": t.symbol,
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "quantity": t.quantity,
                    "side": t.side,
                    "pnl": t.pnl,
                    "pnl_percentage": t.pnl_percentage,
                    "hold_duration_hours": t.hold_duration_hours,
                }
                for t in state.trade_history
            ],
            "total_decisions": state.total_decisions,
            "llm_calls": state.llm_calls,
            "llm_cache_hits": state.llm_cache_hits,
            "equity_curve": state.equity_curve,
            "timestamps": [ts.isoformat() for ts in state.timestamps],
        }

    def _deserialize_execution_state(self, data: Dict[str, Any]) -> ExecutionState:
        """
        反序列化执行状态

        Args:
            data: 序列化的状态字典

        Returns:
            ExecutionState对象
        """
        from vibe_trading.execution.order_executor import PaperPosition
        from vibe_trading.backtest.models import Trade, BacktestDecision
        from vibe_trading.coordinator.signal_processor import TradingSignal

        # 反序列化持仓
        current_positions = {}
        for symbol, pos_data in data.get("current_positions", {}).items():
            current_positions[symbol] = PaperPosition(
                symbol=pos_data["symbol"],
                side=pos_data["side"],
                quantity=pos_data["quantity"],
                entry_price=pos_data["entry_price"],
                unrealized_pnl=pos_data["unrealized_pnl"],
            )

        # 反序列化开放交易
        open_trades = {}
        for trade_id, trade_data in data.get("open_trades", {}).items():
            open_trades[trade_id] = Trade(
                trade_id=trade_data["trade_id"],
                symbol=trade_data["symbol"],
                entry_time=datetime.fromisoformat(trade_data["entry_time"]),
                exit_time=datetime.fromisoformat(trade_data["exit_time"]) if trade_data.get("exit_time") else None,
                entry_price=trade_data["entry_price"],
                exit_price=trade_data["exit_price"],
                quantity=trade_data["quantity"],
                side=trade_data["side"],
                pnl=trade_data["pnl"],
                pnl_percentage=trade_data["pnl_percentage"],
                decision_id=trade_data["decision_id"],
                signal=TradingSignal(trade_data["signal"]),
                confidence=trade_data["confidence"],
                market_condition=trade_data["market_condition"],
                agent_contributions=trade_data.get("agent_contributions", {}),
                hold_duration_hours=trade_data.get("hold_duration_hours", 0.0),
            )

        # 反序列化决策历史（简化版，不包含完整决策对象）
        decision_history = []
        for d_data in data.get("decision_history", []):
            # 创建简化版本的决策对象
            decision = BacktestDecision(
                decision_id=d_data["decision_id"],
                timestamp=datetime.fromisoformat(d_data["timestamp"]),
                current_price=0.0,  # 恢复时不需要
                trading_decision=None,  # 恢复时不需要
                processed_signal=None,  # 恢复时不需要
                agent_contributions={},  # 恢复时不需要
                market_condition="",  # 恢复时不需要
                signal=TradingSignal(d_data["signal"]),
                confidence=d_data["confidence"],
                strength="unknown",
                executed=d_data["executed"],
                trade_id=d_data.get("trade_id"),
            )
            decision_history.append(decision)

        # 反序列化交易历史
        trade_history = []
        for t_data in data.get("trade_history", []):
            trade = Trade(
                trade_id=t_data["trade_id"],
                symbol=t_data["symbol"],
                entry_time=datetime.fromisoformat(t_data["entry_time"]),
                exit_time=datetime.fromisoformat(t_data["exit_time"]) if t_data.get("exit_time") else None,
                entry_price=t_data["entry_price"],
                exit_price=t_data["exit_price"],
                quantity=t_data["quantity"],
                side=t_data["side"],
                pnl=t_data["pnl"],
                pnl_percentage=t_data["pnl_percentage"],
                decision_id="",  # 历史交易不需要
                signal=TradingSignal.HOLD,
                confidence=0.0,
                market_condition="",
                agent_contributions={},
                hold_duration_hours=t_data.get("hold_duration_hours", 0.0),
            )
            trade_history.append(trade)

        # 反序列化时间戳
        timestamps = [
            datetime.fromisoformat(ts) for ts in data.get("timestamps", [])
        ]

        return ExecutionState(
            current_balance=data["current_balance"],
            current_positions=current_positions,
            open_trades=open_trades,
            decision_history=decision_history,
            trade_history=trade_history,
            total_decisions=data["total_decisions"],
            llm_calls=data["llm_calls"],
            llm_cache_hits=data["llm_cache_hits"],
            equity_curve=data.get("equity_curve", []),
            timestamps=timestamps,
        )

    def _serialize_config(self, config: BacktestConfig) -> Dict[str, Any]:
        """序列化配置"""
        return {
            "symbol": config.symbol,
            "interval": config.interval,
            "start_time": config.start_time.isoformat(),
            "end_time": config.end_time.isoformat(),
            "initial_balance": config.initial_balance,
            "llm_mode": config.llm_mode.value,
            "prompt_id": config.prompt_id,
            "prompt_version": config.prompt_version,
            "save_trades": config.save_trades,
            "save_agent_outputs": config.save_agent_outputs,
            "save_to_database": config.save_to_database,
            "report_formats": [f.value for f in config.report_formats],
            "max_concurrent_decisions": config.max_concurrent_decisions,
            "enable_progress_bar": config.enable_progress_bar,
            "save_checkpoints": config.save_checkpoints,
            "checkpoint_interval": config.checkpoint_interval,
            "checkpoint_dir": config.checkpoint_dir,
            "resume_from_checkpoint": config.resume_from_checkpoint,
            "decision_interval": config.decision_interval,
            "significant_change_threshold": config.significant_change_threshold,
        }

    def _deserialize_config(self, data: Dict[str, Any]) -> BacktestConfig:
        """反序列化配置"""
        from vibe_trading.backtest.models import LLMMode, ReportFormat

        return BacktestConfig(
            symbol=data["symbol"],
            interval=data["interval"],
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]),
            initial_balance=data["initial_balance"],
            llm_mode=LLMMode(data["llm_mode"]),
            prompt_id=data.get("prompt_id"),
            prompt_version=data.get("prompt_version"),
            save_trades=data["save_trades"],
            save_agent_outputs=data["save_agent_outputs"],
            save_to_database=data["save_to_database"],
            report_formats=[ReportFormat(f) for f in data.get("report_formats", ["text", "html"])],
            max_concurrent_decisions=data.get("max_concurrent_decisions", 3),
            enable_progress_bar=data.get("enable_progress_bar", True),
            save_checkpoints=data.get("save_checkpoints", False),
            checkpoint_interval=data.get("checkpoint_interval", 100),
            checkpoint_dir=data.get("checkpoint_dir", "./checkpoints"),
            resume_from_checkpoint=data.get("resume_from_checkpoint"),
            decision_interval=data.get("decision_interval", 1),
            significant_change_threshold=data.get("significant_change_threshold", 0.02),
        )

    async def save_checkpoint(
        self,
        checkpoint: BacktestCheckpoint,
    ) -> str:
        """
        保存检查点

        Args:
            checkpoint: 检查点对象

        Returns:
            检查点文件路径
        """
        try:
            checkpoint_path = self._get_checkpoint_path(checkpoint.checkpoint_id)

            # 序列化检查点
            checkpoint_data = {
                "checkpoint_id": checkpoint.checkpoint_id,
                "config": self._serialize_config(checkpoint.config),
                "current_kline_index": checkpoint.current_kline_index,
                "execution_state": checkpoint.execution_state,
                "coordinator_state": checkpoint.coordinator_state,
                "created_at": checkpoint.created_at.isoformat(),
            }

            # 写入文件
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)

            logger.info(f"检查点已保存: {checkpoint_path}")
            return str(checkpoint_path)

        except Exception as e:
            logger.error(f"保存检查点失败: {e}", exc_info=True)
            raise

    async def load_checkpoint(
        self,
        checkpoint_path: str,
    ) -> BacktestCheckpoint:
        """
        加载检查点

        Args:
            checkpoint_path: 检查点文件路径

        Returns:
            检查点对象
        """
        try:
            path = Path(checkpoint_path)
            if not path.exists():
                raise FileNotFoundError(f"检查点文件不存在: {checkpoint_path}")

            # 读取文件
            with open(path, "r", encoding="utf-8") as f:
                checkpoint_data = json.load(f)

            # 反序列化
            checkpoint = BacktestCheckpoint(
                checkpoint_id=checkpoint_data["checkpoint_id"],
                config=self._deserialize_config(checkpoint_data["config"]),
                current_kline_index=checkpoint_data["current_kline_index"],
                execution_state=checkpoint_data["execution_state"],
                coordinator_state=checkpoint_data.get("coordinator_state"),
                created_at=datetime.fromisoformat(checkpoint_data["created_at"]),
            )

            logger.info(f"检查点已加载: {checkpoint_path}")
            return checkpoint

        except Exception as e:
            logger.error(f"加载检查点失败: {e}", exc_info=True)
            raise

    async def list_checkpoints(
        self,
        symbol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        列出所有检查点

        Args:
            symbol: 可选，按品种筛选

        Returns:
            检查点信息列表
        """
        try:
            checkpoints = []

            for checkpoint_file in self.checkpoint_dir.glob("*.json"):
                try:
                    # 读取元数据（不加载完整状态）
                    with open(checkpoint_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    config = data.get("config", {})
                    checkpoint_symbol = config.get("symbol", "")

                    # 筛选
                    if symbol and checkpoint_symbol != symbol:
                        continue

                    checkpoints.append({
                        "checkpoint_id": data["checkpoint_id"],
                        "symbol": checkpoint_symbol,
                        "interval": config.get("interval", ""),
                        "current_kline_index": data["current_kline_index"],
                        "start_time": config.get("start_time", ""),
                        "end_time": config.get("end_time", ""),
                        "created_at": data.get("created_at", ""),
                        "file_path": str(checkpoint_file),
                    })
                except Exception as e:
                    logger.warning(f"无法读取检查点文件 {checkpoint_file}: {e}")
                    continue

            # 按创建时间排序
            checkpoints.sort(key=lambda x: x["created_at"], reverse=True)
            return checkpoints

        except Exception as e:
            logger.error(f"列出检查点失败: {e}", exc_info=True)
            return []

    async def delete_checkpoint(
        self,
        checkpoint_path: str,
    ) -> bool:
        """
        删除检查点

        Args:
            checkpoint_path: 检查点文件路径

        Returns:
            是否删除成功
        """
        try:
            path = Path(checkpoint_path)
            if path.exists():
                path.unlink()
                logger.info(f"检查点已删除: {checkpoint_path}")
                return True
            return False

        except Exception as e:
            logger.error(f"删除检查点失败: {e}", exc_info=True)
            return False

    def generate_checkpoint_id(
        self,
        symbol: str,
        interval: str,
        current_index: int,
    ) -> str:
        """
        生成检查点ID

        Args:
            symbol: 交易品种
            interval: K线间隔
            current_index: 当前K线索引

        Returns:
            检查点ID
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{symbol}_{interval}_kline{current_index}_{timestamp}"
