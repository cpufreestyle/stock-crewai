# -*- coding: utf-8 -*-
"""performance_metrics 纯计算测试

compute_metrics 从 run_virtual_v4.calculate_performance_metrics 抽出，
已对 6 组净值序列与原内联实现做过逐字段等价验证。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from performance_metrics import compute_metrics, read_total_values


class TestComputeMetrics:
    def test_too_few_samples_returns_none(self):
        assert compute_metrics([]) is None
        assert compute_metrics([100000.0]) is None
        assert compute_metrics([100000.0] * 9) is None

    def test_minimum_samples_computes(self):
        m = compute_metrics([100000.0 * (1.001 ** i) for i in range(10)])
        assert m is not None
        assert m["total_days"] == 10

    def test_all_keys_present(self):
        m = compute_metrics([100000.0 * (1.001 ** i) for i in range(15)])
        expected = {"sharpe_ratio", "max_drawdown", "annual_return",
                    "annual_volatility", "win_rate", "total_days",
                    "avg_return_per_trade"}
        assert set(m) == expected

    def test_flat_series_has_zero_metrics(self):
        """净值不变 -> 无收益无波动，夏普为 0，回撤 0"""
        m = compute_metrics([100000.0] * 15)
        assert m["max_drawdown"] == 0
        assert m["sharpe_ratio"] == 0
        assert m["annual_return"] == 0

    def test_zero_prev_value_skipped_not_crash(self):
        """前一笔净值为 0 时跳过该段，不能除零"""
        vals = [100000.0, 0.0] + [100000.0 + i * 10 for i in range(12)]
        m = compute_metrics(vals)
        assert m is not None

    def test_win_rate_counts_only_positive_returns(self):
        up = [100000.0 * (1.01 ** i) for i in range(12)]
        assert compute_metrics(up)["win_rate"] == pytest.approx(100.0)
        down = [100000.0 * (0.99 ** i) for i in range(12)]
        assert compute_metrics(down)["win_rate"] == 0

    def test_max_drawdown_matches_known_case(self):
        # 100 -> 120 -> 60：峰 120 到 60 回撤 50%
        vals = [100.0, 110.0, 120.0, 90.0, 60.0] + [70.0] * 8
        assert compute_metrics(vals)["max_drawdown"] == pytest.approx(50.0)


class TestReadTotalValues:
    def _write_log(self, path, total_value):
        path.write_text(json.dumps(
            {"portfolio": {"total_value": total_value}}), encoding="utf-8")

    def test_reads_in_mtime_order(self, tmp_path):
        for i, v in enumerate([100.0, 110.0, 120.0]):
            self._write_log(tmp_path / f"run_log_{i:04d}.json", v)
        vals = read_total_values(tmp_path)
        assert vals == [100.0, 110.0, 120.0]

    def test_ignores_non_log_files(self, tmp_path):
        self._write_log(tmp_path / "run_log_0001.json", 100.0)
        (tmp_path / "other.json").write_text(json.dumps({"portfolio": {"total_value": 9.0}}),
                                            encoding="utf-8")
        assert read_total_values(tmp_path) == [100.0]

    def test_skips_corrupt_json(self, tmp_path):
        self._write_log(tmp_path / "run_log_0001.json", 100.0)
        (tmp_path / "run_log_0002.json").write_text("{ broken", encoding="utf-8")
        assert read_total_values(tmp_path) == [100.0]

    def test_empty_dir_returns_empty(self, tmp_path):
        assert read_total_values(tmp_path) == []

