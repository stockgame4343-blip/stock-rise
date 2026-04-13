"""APScheduler 기반 데이터 수집 스케줄링"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import COLLECT_HOUR, COLLECT_MINUTE
from collector import collect_and_save

logger = logging.getLogger(__name__)


def create_scheduler():
    """평일 장마감 후 수집 스케줄러 생성"""
    scheduler = BackgroundScheduler()

    # 평일(월~금) 15:35 실행
    trigger = CronTrigger(
        day_of_week='mon-fri',
        hour=COLLECT_HOUR,
        minute=COLLECT_MINUTE,
    )

    scheduler.add_job(
        collect_and_save,
        trigger=trigger,
        id='daily_collect',
        name='일별 상승 종목 수집',
        replace_existing=True,
    )

    logger.info(
        f"스케줄러 등록: 평일 {COLLECT_HOUR:02d}:{COLLECT_MINUTE:02d} 수집 실행"
    )
    return scheduler
