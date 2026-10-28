//! 不直接啟動背景工作的更新排程節流政策。
use std::time::Duration;
pub use wlre_core_observability::ErrorCode as ScheduleError;
const MIN_INTERVAL: Duration = Duration::from_secs(15 * 60);
const MAX_INTERVAL: Duration = Duration::from_secs(7 * 24 * 60 * 60);
const INITIAL_RETRY: Duration = Duration::from_secs(5 * 60);

/// 採單調時間的排程狀態，必須由平台單一執行緒持有並呼叫。
/// 只控制何時允許嘗試，不啟動工作、保存狀態或處理背景權限。
#[derive(Debug)]
pub struct Scheduler {
    interval: Duration,
    next_due: Duration,
    started: Option<Duration>,
    failures: u32,
}
impl Scheduler {
    /// 設定正常間隔，允許 15 分鐘至 7 天，首次於指定時間可嘗試。
    pub fn new(interval: Duration, first_due: Duration) -> Result<Self, ScheduleError> {
        if !(MIN_INTERVAL..=MAX_INTERVAL).contains(&interval) {
            return Err(ScheduleError::ScheduleInvalid);
        }
        Ok(Self {
            interval,
            next_due: first_due,
            started: None,
            failures: 0,
        })
    }
    /// 到期且沒有執行中的工作才取得本次嘗試，避免重疊執行。
    pub fn begin(&mut self, now: Duration) -> bool {
        if self.started.is_some() || now < self.next_due {
            return false;
        }
        self.started = Some(now);
        true
    }
    /// 完成後安排下一次；失敗採有限指數退避，最大不超過正常間隔。
    /// 不接受時間倒退或未開始的完成事件。
    pub fn finish(&mut self, now: Duration, success: bool) -> Result<(), ScheduleError> {
        let started = self.started.ok_or(ScheduleError::ScheduleInvalid)?;
        if now < started {
            return Err(ScheduleError::ScheduleInvalid);
        }
        let (delay, failures) = if success {
            (self.interval, 0)
        } else {
            let failures = self.failures.saturating_add(1);
            let factor = 1u32 << failures.saturating_sub(1).min(16);
            (
                INITIAL_RETRY.saturating_mul(factor).min(self.interval),
                failures,
            )
        };
        let next_due = now
            .checked_add(delay)
            .ok_or(ScheduleError::ScheduleInvalid)?;
        self.next_due = next_due;
        self.failures = failures;
        self.started = None;
        Ok(())
    }
    pub fn next_due(&self) -> Duration {
        self.next_due
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn prevents_overlap_and_retries_with_bounded_backoff() {
        let mut schedule = Scheduler::new(Duration::from_secs(1800), Duration::ZERO).unwrap();
        assert!(schedule.begin(Duration::ZERO));
        assert!(!schedule.begin(Duration::ZERO));
        schedule.finish(Duration::ZERO, false).unwrap();
        assert_eq!(schedule.next_due(), Duration::from_secs(300));
        assert!(!schedule.begin(Duration::from_secs(299)));
        assert!(schedule.begin(Duration::from_secs(300)));
        schedule.finish(Duration::from_secs(300), false).unwrap();
        assert_eq!(schedule.next_due(), Duration::from_secs(900));
        assert!(schedule.begin(Duration::from_secs(900)));
        schedule.finish(Duration::from_secs(900), true).unwrap();
        assert_eq!(schedule.next_due(), Duration::from_secs(2700));
    }
    #[test]
    fn rejects_invalid_interval_and_time_reversal() {
        assert!(Scheduler::new(Duration::from_secs(1), Duration::ZERO).is_err());
        let mut schedule = Scheduler::new(MIN_INTERVAL, Duration::from_secs(10)).unwrap();
        assert!(schedule.begin(Duration::from_secs(10)));
        assert_eq!(
            schedule.finish(Duration::ZERO, true),
            Err(ScheduleError::ScheduleInvalid)
        );
        assert!(!schedule.begin(Duration::from_secs(11)));
        schedule.finish(Duration::from_secs(11), true).unwrap();
    }
}
