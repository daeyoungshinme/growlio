"""estimation.py(축소추정 유틸) 단위 테스트."""

from __future__ import annotations

import random

import numpy as np

from app.services.estimation import shrink_covariance, shrink_expected_returns


class TestShrinkCovariance:
    def test_two_assets_is_noop(self):
        """종목쌍이 하나뿐이면 평균 상관계수 = 그 쌍의 상관계수 자체라 축소해도 목표행렬과
        표본행렬이 동일 — 결과가 원본과 같아야 한다."""
        random.seed(1)
        returns = np.array(
            [
                [random.gauss(0.0005, 0.01) for _ in range(252)],
                [random.gauss(0.0003, 0.008) for _ in range(252)],
            ]
        )
        cov_sample = np.cov(returns) * 252

        shrunk = shrink_covariance(returns, cov_sample)

        assert np.allclose(shrunk, cov_sample, atol=1e-8)

    def test_diagonal_variances_unchanged(self):
        """등상관 목표행렬은 분산(대각)은 표본값 그대로 유지하므로, 축소 후에도 대각은
        불변이어야 한다(비대각 상관관계만 평균 쪽으로 당겨짐)."""
        random.seed(2)
        returns = np.array(
            [
                [random.gauss(0.0005, 0.01) for _ in range(252)],
                [random.gauss(0.0003, 0.008) for _ in range(252)],
                [random.gauss(0.0002, 0.012) for _ in range(252)],
            ]
        )
        cov_sample = np.cov(returns) * 252

        shrunk = shrink_covariance(returns, cov_sample)

        assert np.allclose(np.diag(shrunk), np.diag(cov_sample), atol=1e-8)

    def test_shrinkage_pulls_off_diagonal_toward_average_correlation(self):
        """3종목 이상이면 실제로 비대각 원소가 평균상관 목표 쪽으로 이동해야 한다(표본 그대로와
        달라야 함) — 축소강도가 0이 아님을 확인."""
        random.seed(3)
        returns = np.array(
            [
                [random.gauss(0.0005, 0.01) for _ in range(252)],
                [random.gauss(0.0003, 0.008) for _ in range(252)],
                [random.gauss(0.0002, 0.012) for _ in range(252)],
            ]
        )
        cov_sample = np.cov(returns) * 252

        shrunk = shrink_covariance(returns, cov_sample)

        assert not np.allclose(shrunk, cov_sample, atol=1e-6)

    def test_single_asset_returns_unchanged(self):
        returns = np.array([[0.01] * 252])
        cov_sample = np.array([[0.0004]])

        shrunk = shrink_covariance(returns, cov_sample)

        assert np.allclose(shrunk, cov_sample)

    def test_result_stays_symmetric_and_psd_like(self):
        """축소 결과가 대칭행렬이어야 하고(공분산 행렬의 필수 성질), 대각(분산)은 양수여야 한다."""
        random.seed(4)
        returns = np.array([[random.gauss(0.0004, 0.01) for _ in range(252)] for _ in range(5)])
        cov_sample = np.cov(returns) * 252

        shrunk = shrink_covariance(returns, cov_sample)

        assert np.allclose(shrunk, shrunk.T, atol=1e-10)
        assert np.all(np.diag(shrunk) > 0)


class TestShrinkExpectedReturns:
    def test_fewer_than_three_assets_returns_unchanged(self):
        raw = np.array([5.0, 15.0])
        assert np.array_equal(shrink_expected_returns(raw), raw)

    def test_identical_values_returns_unchanged(self):
        raw = np.array([7.0, 7.0, 7.0])
        shrunk = shrink_expected_returns(raw)
        assert np.allclose(shrunk, raw)

    def test_pulls_extreme_values_toward_grand_mean(self):
        raw = np.array([3.0, 6.0, 15.0])
        shrunk = shrink_expected_returns(raw)

        grand_mean = raw.mean()
        # 축소된 값은 원래 값과 평균 사이에 있어야 하고, 평균에 더 가까워야 한다
        for orig, adj in zip(raw, shrunk, strict=False):
            assert abs(adj - grand_mean) <= abs(orig - grand_mean) + 1e-9
        # 순서(랭킹)는 보존되어야 한다 — 축소는 크기만 완화, 상대적 우열은 유지
        assert shrunk[2] > shrunk[1] > shrunk[0]

    def test_shrinkage_intensity_is_bounded(self):
        """분산이 매우 작아 축소강도가 1을 초과할 수 있는 경우에도 grand_mean을 넘어서
        (부호가 반전되는) 과잉축소가 발생하지 않아야 한다."""
        raw = np.array([7.9, 8.0, 8.1])
        shrunk = shrink_expected_returns(raw)

        grand_mean = raw.mean()
        assert np.allclose(shrunk, grand_mean, atol=1e-6)
