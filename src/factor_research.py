from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "Data" / "CSI300_daily" / "raw"
OUTPUT = ROOT / "output"
FIGURES = OUTPUT / "figures"
TABLES = OUTPUT / "tables"


def mean(values: list[float]) -> float:
    return statistics.mean(values) if values else float("nan")


def stdev(values: list[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else float("nan")


def ranks(values: list[float]) -> list[float]:
    ordered = sorted(range(len(values)), key=lambda index: values[index])
    result = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        rank = (start + end - 1) / 2 + 1
        for position in ordered[start:end]:
            result[position] = rank
        start = end
    return result


def correlation(left: list[float], right: list[float]) -> float:
    if len(left) < 3:
        return float("nan")
    left_mean, right_mean = mean(left), mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left)
        * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator if denominator else float("nan")


def rank_ic(factors: list[float], returns: list[float]) -> float:
    return correlation(ranks(factors), ranks(returns))


def maximum_drawdown(returns: list[float]) -> float:
    wealth = peak = 1.0
    drawdown = 0.0
    for value in returns:
        wealth *= 1 + value
        peak = max(peak, wealth)
        drawdown = min(drawdown, wealth / peak - 1)
    return drawdown


def metrics(returns: list[float], ics: list[float]) -> dict[str, float | int]:
    count = len(returns)
    total = math.prod(1 + value for value in returns) - 1 if count else float("nan")
    annual_return = (1 + total) ** (12 / count) - 1 if count and total > -1 else float("nan")
    annual_volatility = stdev(returns) * math.sqrt(12)
    sharpe = mean(returns) / stdev(returns) * math.sqrt(12) if count > 1 and stdev(returns) else float("nan")
    return {
        "months": count,
        "mean_rank_ic": mean(ics),
        "icir": mean(ics) / stdev(ics) if len(ics) > 1 and stdev(ics) else float("nan"),
        "total_return": total,
        "annual_return": annual_return,
        "annual_volatility": annual_volatility,
        "sharpe_zero_rate": sharpe,
        "max_drawdown": maximum_drawdown(returns),
        "positive_month_ratio": sum(value > 0 for value in returns) / count if count else float("nan"),
    }


class GenerationGroup:
    candidates = {
        "momentum_20d": ("20日动量", "close_t / close_t-20 - 1"),
        "reversal_20d": ("20日反转", "-(close_t / close_t-20 - 1)"),
        "low_volatility_20d": ("20日低波动", "-std(过去20日收益率)"),
    }

    def load(self) -> dict[str, list[tuple[date, float]]]:
        prices: dict[str, dict[date, float]] = defaultdict(dict)
        names: dict[str, str] = {}
        for path in sorted(DATA.glob("*.csv")):
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    close = float(row["close"])
                    if not math.isfinite(close) or close <= 0:
                        raise ValueError(f"非法收盘价: {path} {row['time']}")
                    day = date.fromisoformat(f"{row['time'][:4]}-{row['time'][4:6]}-{row['time'][6:]}")
                    ticker = row["thscode"]
                    if day in prices[ticker]:
                        raise ValueError(f"重复日期: {ticker} {day}")
                    prices[ticker][day] = close
                    names[ticker] = row["thsname_cn"]
        return {ticker: sorted(values.items()) for ticker, values in prices.items()}

    def factor(self, history: list[tuple[date, float]], candidate: str) -> float:
        closes = [value for _, value in history[-21:]]
        if candidate == "momentum_20d":
            return closes[-1] / closes[0] - 1
        if candidate == "reversal_20d":
            return -(closes[-1] / closes[0] - 1)
        daily_returns = [current / previous - 1 for previous, current in zip(closes, closes[1:])]
        return -stdev(daily_returns)

    def prepare(self):
        prices = self.load()
        dates = sorted({day for history in prices.values() for day, _ in history})
        month_ends = []
        for day in dates:
            if not month_ends or (day.year, day.month) != (month_ends[-1].year, month_ends[-1].month):
                month_ends.append(day)
            else:
                month_ends[-1] = day
        lookup = {ticker: dict(history) for ticker, history in prices.items()}
        rows = []
        for current, future in zip(month_ends, month_ends[1:]):
            for ticker, history in prices.items():
                if current not in lookup[ticker] or future not in lookup[ticker]:
                    continue
                past = [item for item in history if item[0] <= current]
                if len(past) < 21:
                    continue
                row = {
                    "date": current.isoformat(),
                    "future_date": future.isoformat(),
                    "ticker": ticker,
                    "future_return": lookup[ticker][future] / lookup[ticker][current] - 1,
                }
                for candidate in self.candidates:
                    row[candidate] = self.factor(past, candidate)
                rows.append(row)
        rebalance_dates = sorted({row["date"] for row in rows})
        test_dates = set(rebalance_dates[-12:])
        return prices, rows, rebalance_dates, test_dates

    def evaluate(self, rows, candidate, dates):
        monthly = []
        for day in dates:
            selected = [row for row in rows if row["date"] == day]
            if len(selected) < 10:
                continue
            factors = [row[candidate] for row in selected]
            returns = [row["future_return"] for row in selected]
            ordered = sorted(range(len(selected)), key=lambda index: factors[index])
            groups = [[] for _ in range(5)]
            for position, index in enumerate(ordered):
                groups[min(4, position * 5 // len(selected))].append(returns[index])
            group_returns = [mean(group) for group in groups]
            monthly.append({
                "date": day,
                "future_date": selected[0]["future_date"],
                "stocks": len(selected),
                "rank_ic": rank_ic(factors, returns),
                "groups": group_returns,
                "long_short": group_returns[4] - group_returns[0],
                "equal_weight": mean(returns),
            })
        return monthly


class CheckingGroup:
    def review(self, rows, monthly, selected_monthly, test_dates) -> list[dict]:
        reconciled = math.isclose(
            metrics([row["long_short"] for row in monthly], [row["rank_ic"] for row in monthly])["total_return"],
            math.prod(1 + row["long_short"] for row in monthly) - 1,
            abs_tol=1e-12,
        )
        return [
            {"check": "信号与收益错位", "passed": all(row["future_date"] > row["date"] for row in rows)},
            {"check": "每月至少10只股票", "passed": all(row["stocks"] >= 10 for row in selected_monthly)},
            {"check": "样本外隔离", "passed": len(test_dates) == 12 and all(row["date"] in test_dates for row in monthly[-12:])},
            {"check": "收益独立复算", "passed": reconciled},
            {"check": "有限数值", "passed": all(math.isfinite(row["long_short"]) for row in selected_monthly)},
        ]


class AllocationGroup:
    def run(self):
        generator = GenerationGroup()
        prices, rows, dates, test_dates = generator.prepare()
        train_dates = [day for day in dates if day not in test_dates]
        candidates = []
        for key, (name, formula) in generator.candidates.items():
            train = generator.evaluate(rows, key, train_dates)
            candidates.append({
                "key": key,
                "name": name,
                "formula": formula,
                "train_mean_rank_ic": mean([row["rank_ic"] for row in train]),
                "train_icir": metrics([row["long_short"] for row in train], [row["rank_ic"] for row in train])["icir"],
            })
        chosen = max(candidates, key=lambda item: item["train_mean_rank_ic"])
        monthly = generator.evaluate(rows, chosen["key"], dates)
        train = [row for row in monthly if row["date"] not in test_dates]
        test = [row for row in monthly if row["date"] in test_dates]

        def summarize(part):
            return {
                "long_short": metrics([row["long_short"] for row in part], [row["rank_ic"] for row in part]),
                "equal_weight": metrics([row["equal_weight"] for row in part], [row["rank_ic"] for row in part]),
                "quintile_annual_returns": [
                    (math.prod(1 + row["groups"][index] for row in part) ** (12 / len(part)) - 1)
                    for index in range(5)
                ],
            }

        checks = CheckingGroup().review(rows, test, monthly, test_dates)
        return {
            "report_date": date.today().isoformat(),
            "data": {
                "files": len(list(DATA.glob("*.csv"))),
                "tickers": len(prices),
                "price_rows": sum(len(history) for history in prices.values()),
                "start": min(day for history in prices.values() for day, _ in history).isoformat(),
                "end": max(day for history in prices.values() for day, _ in history).isoformat(),
                "rebalance_months": len(monthly),
                "train_months": len(train),
                "test_months": len(test),
                "currency": "CNY",
            },
            "candidates": candidates,
            "selected": chosen,
            "train": summarize(train),
            "test": summarize(test),
            "monthly": monthly,
            "checks": checks,
            "approved": all(item["passed"] for item in checks),
            "limitations": [
                "仅覆盖34只创业板股票，不能代表完整沪深300或全部A股",
                "使用当前成分名单，存在幸存者偏差",
                "收盘价是否复权未确认，未计入分红",
                "未计手续费、滑点、涨跌停和做空约束",
                "三个候选共享同一样本，样本外结果仍需更多数据验证",
            ],
        }


class UpdateSystem:
    def save(self, result):
        OUTPUT.mkdir(exist_ok=True)
        FIGURES.mkdir(exist_ok=True)
        TABLES.mkdir(exist_ok=True)
        (OUTPUT / "factor_results.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
        with (OUTPUT / "monthly_returns.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["factor_date", "return_date", "stocks", "rank_ic", "Q1", "Q2", "Q3", "Q4", "Q5", "long_short", "equal_weight"])
            for row in result["monthly"]:
                writer.writerow([row["date"], row["future_date"], row["stocks"], row["rank_ic"], *row["groups"], row["long_short"], row["equal_weight"]])
        self.figures(result)

    def figures(self, result):
        test = [row for row in result["monthly"] if row["date"] >= sorted({r["date"] for r in result["monthly"]})[-12]]
        values = result["test"]["quintile_annual_returns"]
        bars = "\n".join(f"({label},{value * 100:.4f})" for label, value in zip(["Q1", "Q2", "Q3", "Q4", "Q5"], values))
        (FIGURES / "quintile_returns.tex").write_text(r"""\begin{tikzpicture}
\begin{axis}[ybar,width=\linewidth,height=48mm,bar width=12pt,symbolic x coords={Q1,Q2,Q3,Q4,Q5},xtick=data,ylabel={年化收益率（\%）},grid=major,grid style={gray!20},every axis label/.style={font=\small},tick label style={font=\small}]
\addplot[fill=MemoBlue,draw=none] coordinates {
""" + bars + r"""
};
\end{axis}
\end{tikzpicture}
""", encoding="utf-8")
        wealth_long, wealth_market = 100.0, 100.0
        points_long, points_market = [], []
        for row in test:
            wealth_long *= 1 + row["long_short"]
            wealth_market *= 1 + row["equal_weight"]
            points_long.append(f"({row['future_date']},{wealth_long:.4f})")
            points_market.append(f"({row['future_date']},{wealth_market:.4f})")
        (FIGURES / "oos_wealth.tex").write_text(r"""\begin{tikzpicture}
\begin{axis}[width=\linewidth,height=55mm,date coordinates in=x,xticklabel={\year-\month},xticklabel style={rotate=35,anchor=east,font=\scriptsize},ylabel={净值（起点=100）},grid=major,grid style={gray!20},legend style={at={(0.02,0.98)},anchor=north west,font=\scriptsize},every axis label/.style={font=\small}]
\addplot[MemoBlue,thick] coordinates {
""" + "\n".join(points_long) + r"""
};
\addlegendentry{多空组合}
\addplot[orange,thick] coordinates {
""" + "\n".join(points_market) + r"""
};
\addlegendentry{等权基准}
\end{axis}
\end{tikzpicture}
""", encoding="utf-8")


if __name__ == "__main__":
    research = AllocationGroup().run()
    UpdateSystem().save(research)
    print(json.dumps({
        "selected": research["selected"],
        "data": research["data"],
        "test": research["test"],
        "approved": research["approved"],
    }, ensure_ascii=False, indent=2))
