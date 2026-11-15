from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

DEMO_PRICES = [100.0, 101.0, 100.0, 102.0, 103.0, 102.0, 104.0]
STATE_PATH = Path.cwd() / ".qt" / "state.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def maximum_drawdown(equity: list[float]) -> float:
    peak = equity[0]
    drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        drawdown = max(drawdown, (peak - value) / peak)
    return drawdown


class GenerationGroup:
    def generate(self, prices: list[float], data_source: str) -> dict[str, Any]:
        if len(prices) < 4 or any(
            isinstance(price, bool) or not math.isfinite(price) or price <= 0
            for price in prices
        ):
            raise ValueError("价格序列至少需要 4 个有限正数")

        returns = [current / previous - 1 for previous, current in zip(prices, prices[1:])]
        positions = [0.0] + [1.0 if value > 0 else 0.0 for value in returns[:-1]]
        strategy_returns = [position * value for position, value in zip(positions, returns)]
        equity = [1.0]
        for value in strategy_returns:
            equity.append(equity[-1] * (1.0 + value))

        return {
            "data": {
                "source": data_source,
                "observations": len(prices),
                "missing_values": 0,
            },
            "features": {"return_count": len(returns), "signal_lag": 1},
            "backtest": {
                "total_return": round(equity[-1] - 1.0, 8),
                "max_drawdown": round(maximum_drawdown(equity), 8),
                "equity_curve": [round(value, 8) for value in equity],
            },
            "assumptions": ["不计手续费和滑点", "上一期收益决定本期仓位，避免前视偏差"],
        }


class CheckingGroup:
    def review(self, draft: dict[str, Any]) -> dict[str, Any]:
        backtest = draft["backtest"]
        curve = backtest["equity_curve"]
        checks = [
            {
                "name": "样本量",
                "passed": draft["data"]["observations"] >= 4,
                "detail": "至少需要 4 个价格观测值",
            },
            {
                "name": "信号滞后",
                "passed": draft["features"]["signal_lag"] == 1,
                "detail": "交易信号必须滞后一期",
            },
            {
                "name": "回撤复算",
                "passed": math.isclose(
                    maximum_drawdown(curve), backtest["max_drawdown"], abs_tol=1e-7
                ),
                "detail": "独立复算权益曲线的最大回撤",
            },
            {
                "name": "风险上限",
                "passed": backtest["max_drawdown"] <= 0.20,
                "detail": "最大回撤不得超过 20%",
            },
        ]
        return {
            "approved": all(check["passed"] for check in checks),
            "checks": checks,
            "note": "检查通过仅表示框架规则通过，不代表策略适合实盘",
        }


class AllocationGroup:
    def __init__(self, state: dict[str, Any], save: Any) -> None:
        self.state = state
        self.save = save
        self.generator = GenerationGroup()
        self.checker = CheckingGroup()

    def run(self, task: str, prices: list[float], data_source: str) -> dict[str, Any]:
        record: dict[str, Any] = {
            "id": uuid4().hex[:8],
            "task": task,
            "created_at": now(),
            "status": "running",
        }
        self.state["tasks"].append(record)
        groups = self.state["research_layer"]["groups"]
        groups["allocation"] = "running"
        self.save()

        try:
            groups["generation"] = "running"
            self.save()
            draft = self.generator.generate(prices, data_source)
            record["draft"] = draft
            groups["generation"] = "done"

            groups["checking"] = "running"
            self.save()
            review = self.checker.review(draft)
            record["review"] = review
            groups["checking"] = "done"
            record["status"] = "approved" if review["approved"] else "rejected"
        except Exception as error:
            record["status"] = "failed"
            record["error"] = str(error)
            groups["generation"] = "idle"
            groups["checking"] = "idle"
            groups["allocation"] = "ready"
            self.save()
            raise

        groups["allocation"] = "ready"
        self.state["research_layer"]["last_task_id"] = record["id"]
        self.save()
        return record


class UpdateSystem:
    def __init__(self, path: Path = STATE_PATH) -> None:
        self.path = path
        self.state = self._load()
        self.allocator = AllocationGroup(self.state, self.save)

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {
            "research_layer": {
                "leader": "allocation",
                "groups": {"allocation": "ready", "generation": "idle", "checking": "idle"},
                "last_task_id": None,
            },
            "update_layer": {"status": "ready", "last_command": None},
            "tasks": [],
            "commands": [],
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(self.path)

    def run(self, task: str, prices: list[float] | None = None) -> dict[str, Any]:
        source = "user-supplied" if prices is not None else "synthetic-demo"
        return self.allocator.run(task, prices or DEMO_PRICES, source)

    def command(self, text: str) -> dict[str, Any]:
        if not text.strip():
            raise ValueError("指令不能为空")
        record = {"text": text, "received_at": now(), "status": "accepted"}
        self.state["commands"].append(record)
        self.state["update_layer"]["last_command"] = record
        self.save()
        return record


def parse_prices(value: str | None) -> list[float] | None:
    if value is None:
        return None
    try:
        return [float(item.strip()) for item in value.split(",")]
    except ValueError as error:
        raise ValueError("--prices 必须是逗号分隔的数字") from error


def main() -> int:
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="两层量化研究团队框架")
    subparsers = parser.add_subparsers(dest="action", required=True)
    run_parser = subparsers.add_parser("run", help="由分配组运行一次研究流程")
    run_parser.add_argument("task", help="研究任务描述")
    run_parser.add_argument("--prices", help="逗号分隔的价格；省略则使用合成示例数据")
    subparsers.add_parser("status", help="获取整个系统状态")
    command_parser = subparsers.add_parser("command", help="向更新层提交用户指令")
    command_parser.add_argument("text", help="指令内容")
    args = parser.parse_args()

    system = UpdateSystem()
    try:
        if args.action == "run":
            result = system.run(args.task, parse_prices(args.prices))
        elif args.action == "command":
            result = system.command(args.text)
        else:
            result = system.state
    except (ValueError, OSError, json.JSONDecodeError) as error:
        parser.exit(1, f"错误: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
