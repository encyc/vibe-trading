"""
并行执行器

优化可并行执行的Agent，提升系统性能。
"""
import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """执行结果"""
    agent_name: str
    success: bool
    result: Any
    error: Optional[str] = None
    execution_time: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


@dataclass
class PhaseExecutionSummary:
    """阶段执行摘要"""
    phase_name: str
    total_agents: int
    successful: int
    failed: int
    total_time: float
    parallel_speedup: float
    results: List[ExecutionResult]


class ParallelExecutor:
    """
    并行执行器

    管理Agent的并行执行，处理异常和超时。
    """

    def __init__(self):
        self.execution_history: List[PhaseExecutionSummary] = []

    async def run_phase_1_analysts(
        self,
        analysts: List[Any],
        context: Dict,
        timeout_per_agent: float = 60.0,
    ) -> PhaseExecutionSummary:
        """
        Phase 1: 分析师团队并行执行

        Args:
            analysts: 分析师Agent列表
            context: 执行上下文
            timeout_per_agent: 每个Agent的超时时间（秒）

        Returns:
            阶段执行摘要
        """
        logger.info(f"Starting Phase 1: {len(analysts)} analysts in parallel")
        start_time = datetime.now()

        # 创建任务
        tasks = []
        for analyst in analysts:
            task = self._run_agent_with_timeout(
                agent=analyst,
                agent_name=analyst.name,
                context=context,
                timeout=timeout_per_agent,
            )
            tasks.append(task)

        # 并行执行
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        execution_results = []
        successful = 0
        failed = 0

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Analyst {analysts[i].name} failed: {result}")
                execution_results.append(ExecutionResult(
                    agent_name=analysts[i].name,
                    success=False,
                    result=None,
                    error=str(result),
                ))
                failed += 1
            elif isinstance(result, ExecutionResult):
                execution_results.append(result)
                if result.success:
                    successful += 1
                else:
                    failed += 1

        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()

        # 计算加速比
        sequential_time = len(analysts) * timeout_per_agent
        parallel_speedup = sequential_time / total_time if total_time > 0 else 1.0

        summary = PhaseExecutionSummary(
            phase_name="Phase 1: Analysts",
            total_agents=len(analysts),
            successful=successful,
            failed=failed,
            total_time=total_time,
            parallel_speedup=parallel_speedup,
            results=execution_results,
        )

        self.execution_history.append(summary)

        logger.info(
            f"Phase 1 completed: {successful}/{len(analysts)} successful, "
            f"time={total_time:.2f}s, speedup={parallel_speedup:.2f}x"
        )

        return summary

    async def run_phase_3_risk_agents(
        self,
        risk_agents: List[Any],
        context: Dict,
        timeout_per_agent: float = 30.0,
    ) -> PhaseExecutionSummary:
        """
        Phase 3: 风控团队并行执行

        Args:
            risk_agents: 风控Agent列表
            context: 执行上下文
            timeout_per_agent: 每个Agent的超时时间

        Returns:
            阶段执行摘要
        """
        logger.info(f"Starting Phase 3: {len(risk_agents)} risk agents in parallel")
        start_time = datetime.now()

        tasks = []
        for agent in risk_agents:
            task = self._run_agent_with_timeout(
                agent=agent,
                agent_name=agent.name,
                context=context,
                timeout=timeout_per_agent,
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        execution_results = []
        successful = 0
        failed = 0

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Risk agent {risk_agents[i].name} failed: {result}")
                execution_results.append(ExecutionResult(
                    agent_name=risk_agents[i].name,
                    success=False,
                    result=None,
                    error=str(result),
                ))
                failed += 1
            elif isinstance(result, ExecutionResult):
                execution_results.append(result)
                if result.success:
                    successful += 1
                else:
                    failed += 1

        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()

        sequential_time = len(risk_agents) * timeout_per_agent
        parallel_speedup = sequential_time / total_time if total_time > 0 else 1.0

        summary = PhaseExecutionSummary(
            phase_name="Phase 3: Risk Agents",
            total_agents=len(risk_agents),
            successful=successful,
            failed=failed,
            total_time=total_time,
            parallel_speedup=parallel_speedup,
            results=execution_results,
        )

        self.execution_history.append(summary)

        logger.info(
            f"Phase 3 completed: {successful}/{len(risk_agents)} successful, "
            f"time={total_time:.2f}s, speedup={parallel_speedup:.2f}x"
        )

        return summary

    async def run_parallel_with_dependencies(
        self,
        tasks: List[Tuple[str, Callable, List[str]]],
        context: Dict,
        timeout: float = 60.0,
    ) -> PhaseExecutionSummary:
        """
        运行有依赖关系的并行任务

        Args:
            tasks: 任务列表，每个任务为 (name, func, dependencies)
            context: 执行上下文
            timeout: 超时时间

        Returns:
            阶段执行摘要
        """
        logger.info(f"Starting {len(tasks)} tasks with dependencies")
        start_time = datetime.now()

        # 构建依赖图
        task_map = {name: (func, deps) for name, func, deps in tasks}
        completed = set()
        results = {}
        execution_results = []

        while len(completed) < len(tasks):
            # 找出可以执行的任务（依赖已满足）
            ready_tasks = [
                (name, func)
                for name, func, deps in tasks
                if name not in completed and all(d in completed for d in deps)
            ]

            if not ready_tasks:
                logger.error("Circular dependency detected or no tasks ready")
                break

            # 并行执行就绪任务
            current_tasks = []
            for name, func in ready_tasks:
                task = self._run_function_with_timeout(
                    func=func,
                    task_name=name,
                    context=context,
                    timeout=timeout,
                )
                current_tasks.append(task)

            current_results = await asyncio.gather(*current_tasks, return_exceptions=True)

            # 处理结果
            for i, result in enumerate(current_results):
                name = ready_tasks[i][0]
                completed.add(name)

                if isinstance(result, Exception):
                    logger.error(f"Task {name} failed: {result}")
                    execution_results.append(ExecutionResult(
                        agent_name=name,
                        success=False,
                        result=None,
                        error=str(result),
                    ))
                elif isinstance(result, ExecutionResult):
                    execution_results.append(result)
                    results[name] = result.result

        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()

        successful = sum(1 for r in execution_results if r.success)
        failed = len(execution_results) - successful

        summary = PhaseExecutionSummary(
            phase_name="Parallel with Dependencies",
            total_agents=len(tasks),
            successful=successful,
            failed=failed,
            total_time=total_time,
            parallel_speedup=1.0,  # 无法准确计算
            results=execution_results,
        )

        self.execution_history.append(summary)

        return summary

    async def _run_agent_with_timeout(
        self,
        agent: Any,
        agent_name: str,
        context: Dict,
        timeout: float,
    ) -> ExecutionResult:
        """运行Agent（带超时）"""
        start_time = datetime.now()

        try:
            # 尝试调用agent的analyze或respond方法
            if hasattr(agent, 'analyze'):
                result = await asyncio.wait_for(
                    agent.analyze(context),
                    timeout=timeout,
                )
            elif hasattr(agent, 'respond'):
                result = await asyncio.wait_for(
                    agent.respond(context),
                    timeout=timeout,
                )
            elif hasattr(agent, 'assess'):
                result = await asyncio.wait_for(
                    agent.assess(context),
                    timeout=timeout,
                )
            else:
                raise AttributeError(f"Agent {agent_name} has no callable method")

            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            return ExecutionResult(
                agent_name=agent_name,
                success=True,
                result=result,
                execution_time=execution_time,
                start_time=start_time,
                end_time=end_time,
            )

        except asyncio.TimeoutError:
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            logger.warning(f"Agent {agent_name} timed out after {timeout}s")

            return ExecutionResult(
                agent_name=agent_name,
                success=False,
                result=None,
                error=f"Timeout after {timeout}s",
                execution_time=execution_time,
                start_time=start_time,
                end_time=end_time,
            )

        except Exception as e:
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            logger.error(f"Agent {agent_name} failed: {e}")

            return ExecutionResult(
                agent_name=agent_name,
                success=False,
                result=None,
                error=str(e),
                execution_time=execution_time,
                start_time=start_time,
                end_time=end_time,
            )

    async def _run_function_with_timeout(
        self,
        func: Callable,
        task_name: str,
        context: Dict,
        timeout: float,
    ) -> ExecutionResult:
        """运行函数（带超时）"""
        start_time = datetime.now()

        try:
            result = await asyncio.wait_for(
                func(context),
                timeout=timeout,
            )

            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            return ExecutionResult(
                agent_name=task_name,
                success=True,
                result=result,
                execution_time=execution_time,
                start_time=start_time,
                end_time=end_time,
            )

        except asyncio.TimeoutError:
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            return ExecutionResult(
                agent_name=task_name,
                success=False,
                result=None,
                error=f"Timeout after {timeout}s",
                execution_time=execution_time,
                start_time=start_time,
                end_time=end_time,
            )

        except Exception as e:
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            return ExecutionResult(
                agent_name=task_name,
                success=False,
                result=None,
                error=str(e),
                execution_time=execution_time,
                start_time=start_time,
                end_time=end_time,
            )

    def get_performance_stats(self) -> Dict:
        """获取性能统计"""
        if not self.execution_history:
            return {}

        total_phases = len(self.execution_history)
        total_agents = sum(s.total_agents for s in self.execution_history)
        total_successful = sum(s.successful for s in self.execution_history)
        total_failed = sum(s.failed for s in self.execution_history)

        avg_speedup = sum(s.parallel_speedup for s in self.execution_history) / total_phases
        avg_time = sum(s.total_time for s in self.execution_history) / total_phases

        return {
            "total_phases": total_phases,
            "total_agents": total_agents,
            "total_successful": total_successful,
            "total_failed": total_failed,
            "success_rate": total_successful / total_agents if total_agents > 0 else 0,
            "avg_speedup": avg_speedup,
            "avg_time": avg_time,
        }


class SequentialExecutor:
    """
    串行执行器 - 用于对比和调试

    串行执行所有Agent，便于调试和性能对比。
    """

    async def run_sequential(
        self,
        agents: List[Any],
        context: Dict,
        timeout_per_agent: float = 60.0,
    ) -> PhaseExecutionSummary:
        """串行执行Agent"""
        logger.info(f"Starting sequential execution: {len(agents)} agents")
        start_time = datetime.now()

        execution_results = []
        successful = 0
        failed = 0

        for agent in agents:
            result = await self._run_agent_with_timeout(
                agent=agent,
                agent_name=agent.name,
                context=context,
                timeout=timeout_per_agent,
            )

            execution_results.append(result)

            if result.success:
                successful += 1
            else:
                failed += 1

        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()

        summary = PhaseExecutionSummary(
            phase_name="Sequential Execution",
            total_agents=len(agents),
            successful=successful,
            failed=failed,
            total_time=total_time,
            parallel_speedup=1.0,
            results=execution_results,
        )

        logger.info(
            f"Sequential execution completed: {successful}/{len(agents)} successful, "
            f"time={total_time:.2f}s"
        )

        return summary

    async def _run_agent_with_timeout(
        self,
        agent: Any,
        agent_name: str,
        context: Dict,
        timeout: float,
    ) -> ExecutionResult:
        """运行Agent（带超时）"""
        start_time = datetime.now()

        try:
            if hasattr(agent, 'analyze'):
                result = await asyncio.wait_for(
                    agent.analyze(context),
                    timeout=timeout,
                )
            elif hasattr(agent, 'respond'):
                result = await asyncio.wait_for(
                    agent.respond(context),
                    timeout=timeout,
                )
            elif hasattr(agent, 'assess'):
                result = await asyncio.wait_for(
                    agent.assess(context),
                    timeout=timeout,
                )
            else:
                raise AttributeError(f"Agent {agent_name} has no callable method")

            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            return ExecutionResult(
                agent_name=agent_name,
                success=True,
                result=result,
                execution_time=execution_time,
                start_time=start_time,
                end_time=end_time,
            )

        except Exception as e:
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            return ExecutionResult(
                agent_name=agent_name,
                success=False,
                result=None,
                error=str(e),
                execution_time=execution_time,
                start_time=start_time,
                end_time=end_time,
            )


# 全局单例
_parallel_executor = ParallelExecutor()


def get_parallel_executor() -> ParallelExecutor:
    """获取全局并行执行器"""
    return _parallel_executor
