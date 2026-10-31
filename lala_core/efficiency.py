"""伺服器來源經驗樣本的速率與升級預估，未取得樣本時不產生估算。"""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExperienceSample:
    observed_seconds: float
    total_experience: int


@dataclass(frozen=True, slots=True)
class ExperienceEstimate:
    experience_per_hour: float
    hours_to_target: float | None


def estimate_experience(first: ExperienceSample, last: ExperienceSample,
                        target_total_experience: int | None = None) -> ExperienceEstimate:
    if (first.observed_seconds < 0 or last.observed_seconds <= first.observed_seconds or
            any(type(x.total_experience) is not int or x.total_experience < 0
                for x in (first, last))):
        raise ValueError("樣本時間或累積經驗值無效")
    gained = last.total_experience - first.total_experience
    if gained < 0:
        raise ValueError("經驗累積值下降，可能已換角色或資料重新初始化")
    rate = gained * 3600 / (last.observed_seconds - first.observed_seconds)
    hours = None
    if target_total_experience is not None:
        if type(target_total_experience) is not int or target_total_experience < 0:
            raise ValueError("經驗目標無效")
        remaining = max(0, target_total_experience - last.total_experience)
        hours = 0.0 if remaining == 0 else remaining / rate if rate > 0 else None
    return ExperienceEstimate(rate, hours)
