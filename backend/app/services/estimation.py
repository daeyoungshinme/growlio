"""MVO 입력(기대수익률·공분산) 축소추정(shrinkage estimation) 유틸.

표본 평균·표본 공분산을 그대로 MVO에 넣으면 추정오차(특히 종목 수 대비 관측치가 적을 때)가
그대로 최적화 결과에 반영돼 과최적화(overfitting)된 극단적 비중을 만들기 쉽다 — 여기 함수들은
`goal_portfolio_optimizer.py`/`portfolio_optimizer.py`가 표본 추정치 대신 사용하는 축소추정
버전을 제공한다. DB·외부 API 의존 없는 순수 계산이라 두 최적화 엔진이 공용으로 쓴다.
"""

from __future__ import annotations

import numpy as np

_MIN_ASSETS_FOR_COV_SHRINKAGE = 2
_MIN_ASSETS_FOR_MEAN_SHRINKAGE = 3
_ASSUMED_RETURN_NOISE_VAR_PCT2 = 25.0
"""연율화 CAGR(%) 추정치 하나의 "가정된" 노이즈 분산(표준편차 ≈5%p) — 1년치 일별 수익률로 추정한
연율화 평균수익률의 추정오차 크기를 나타내는 고정값이다. 원조 James-Stein(1961) 추정량은 원래
노이즈 분산이 (데이터와 무관하게) 알려져 있다고 가정하는 형태다 — 여기서도 `raw_means` 자체의
표본분산을 노이즈 추정치로 재사용하면 분자·분모가 항상 동일 비율로 상쇄돼(둘 다 같은 데이터의
분산에서 나오므로) 축소강도가 데이터와 무관한 상수가 돼버리는 순환 논리에 빠진다 — 그래서
데이터와 독립적인 고정 가정값을 쓴다."""


def shrink_covariance(returns: np.ndarray, cov_sample: np.ndarray) -> np.ndarray:
    """Ledoit-Wolf 등상관(constant correlation) 목표 축소추정.

    Ledoit & Wolf(2003, "Improved estimation of the covariance matrix of stock returns
    with an application to portfolio selection")의 닫힌형(closed-form) 공식을 직접 구현했다
    (sklearn 등 외부 의존성 없이 종목 수가 적은 이 서비스 특성상 구현 부담이 낮음).

    표본 공분산(`cov_sample`)과, 모든 종목쌍이 동일한 평균 상관계수를 갖는다고 가정한 목표
    행렬(target — 분산은 표본값 그대로, 상관계수만 평균으로 통일) 사이를 축소강도
    (shrinkage intensity, 0~1 — 표본 크기가 작고 종목 수가 많을수록 1에 가까워짐)로 보간한다.
    분산(대각)은 표본 추정이 상대적으로 안정적이라 그대로 유지하고, 노이즈가 큰 공분산(비대각,
    종목 간 상관관계)만 평균 쪽으로 당기는 것이 이 방법의 핵심.

    `returns`: (N, T) 종목별 수익률 배열(원본 스케일 — 연율화 여부 무관, `cov_sample` 계산에
    쓰인 것과 동일한 배열이어야 함). `cov_sample`: (N, N) 공분산 행렬 — 이 함수는 축소강도를
    `returns`에서 직접 계산하되(축소강도 자체는 스케일 불변) 최종 블렌딩은 `cov_sample`의
    스케일(예: 연율화된 값)을 그대로 유지해 반환한다.
    """
    n, t = returns.shape
    if n < _MIN_ASSETS_FOR_COV_SHRINKAGE or t < 3:
        return cov_sample

    x = returns.T  # (T, N)
    x = x - x.mean(axis=0, keepdims=True)
    s = (x.T @ x) / t  # (N, N) — 축소강도 계산 전용 표본공분산(원본 스케일, MLE)

    var = np.diag(s)
    std = np.sqrt(np.maximum(var, 1e-18))
    corr = s / np.outer(std, std)
    off_diag = ~np.eye(n, dtype=bool)
    rbar = float(corr[off_diag].mean())

    target = rbar * np.outer(std, std)
    np.fill_diagonal(target, var)

    gamma_hat = float(((target - s) ** 2).sum())
    if gamma_hat < 1e-18:
        return cov_sample

    outer_products = np.einsum("ti,tj->tij", x, x)  # (T, N, N), Γ_t[i,j] = x_it * x_jt
    pi_mat = ((outer_products - s) ** 2).mean(axis=0)  # (N, N)
    pi_hat = float(pi_mat.sum())

    rho_hat = float(np.trace(pi_mat))
    x_sq = x**2
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            asy_cov_ii_ij = float(np.mean((x_sq[:, i] - var[i]) * (x[:, i] * x[:, j] - s[i, j])))
            asy_cov_jj_ij = float(np.mean((x_sq[:, j] - var[j]) * (x[:, i] * x[:, j] - s[i, j])))
            rho_hat += (rbar / 2.0) * (
                np.sqrt(var[j] / var[i]) * asy_cov_ii_ij + np.sqrt(var[i] / var[j]) * asy_cov_jj_ij
            )

    kappa_hat = (pi_hat - rho_hat) / gamma_hat
    shrinkage = float(np.clip(kappa_hat / t, 0.0, 1.0))

    var_out = np.diag(cov_sample)
    std_out = np.sqrt(np.maximum(var_out, 1e-18))
    target_out = rbar * np.outer(std_out, std_out)
    np.fill_diagonal(target_out, var_out)

    return shrinkage * target_out + (1.0 - shrinkage) * cov_sample


def shrink_expected_returns(raw_means: np.ndarray) -> np.ndarray:
    """James-Stein류 축소추정 — 종목별 기대수익률(예: 연율화 CAGR%)을 횡단면 평균 쪽으로 당긴다.

    개별 종목의 과거 평균 수익률은 공분산보다 추정오차가 훨씬 커서(자산가격의 평균은 분산보다
    추정하기 어렵다는 것이 잘 알려진 사실), 표본 평균을 그대로 MVO에 넣으면 우연히 과거 수익률이
    높았던 종목에 과도하게 쏠리는 결과를 만들기 쉽다. James-Stein 추정량은 각 종목 값을 전체
    평균(grand mean) 쪽으로 당겨 이런 극단치의 영향을 완화하며, 종목 수(n)가 3 이상일 때만
    의미가 있다(James-Stein의 고전적 결과 자체가 n>=3에서만 표본평균보다 우월함이 증명됨).

    축소강도(shrinkage intensity) = `(n-2) * sigma^2 / Σ(x_i - x_bar)^2` — `sigma^2`는 개별
    추정치의 노이즈 분산으로, 원조 James-Stein(1961) 공식대로 데이터와 무관한 고정
    가정값(`_ASSUMED_RETURN_NOISE_VAR_PCT2`)을 쓴다. `raw_means` 자체의 표본분산을 노이즈
    추정치로 재사용하면(분자·분모 모두 같은 데이터의 분산에서 유도되어) 축소강도가 사실상
    `(n-2)/(n-1)` 상수로 상쇄되어버려 실제 값의 극단성과 무관해지는 순환 논리 버그가 생긴다.
    """
    n = raw_means.shape[0]
    if n < _MIN_ASSETS_FOR_MEAN_SHRINKAGE:
        return raw_means

    grand_mean = float(raw_means.mean())
    deviations = raw_means - grand_mean
    dispersion = float((deviations**2).sum())
    if dispersion < 1e-12:
        return raw_means

    shrink_factor = min(1.0, max(0.0, (n - 2) * _ASSUMED_RETURN_NOISE_VAR_PCT2 / dispersion))
    return raw_means - shrink_factor * deviations
