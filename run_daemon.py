#!/usr/bin/env python3
"""
OpenClaw Trading OS — 后台守护进程入口

启动方式：
    python3 run_daemon.py

功能：
    - 市场时段感知价格轮询（60s 盘中 / 300s 收盘）
    - 自选股止损 / 目标价预警（写入 alerts_log）
    - 使用 APScheduler BlockingScheduler（主线程阻塞，SIGINT 优雅退出）
"""
import logging
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from daemon.price_poller import poll_once, _store
from daemon.scheduler import get_poll_interval, market_status_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("trading-os-daemon")

scheduler = BlockingScheduler(timezone="UTC")


def dynamic_poll():
    """轮询任务：先拉价格触发预警，再根据市场状态动态调整下次间隔。"""
    symbols = list(_store.get_all_watched_symbols().keys())
    if not symbols:
        logger.info("[Daemon] 自选列表为空，跳过轮询")
        return

    # 显示市场状态
    status = market_status_summary(symbols)
    logger.info(f"[Daemon] 市场状态: {status}")

    # 执行轮询
    results = poll_once()
    logger.info(f"[Daemon] 轮询完成，获取 {len(results)} 只标的价格")

    # 动态调整轮询间隔
    interval = get_poll_interval(symbols)
    job = scheduler.get_job("poll")
    if job:
        current = job.trigger.interval.total_seconds()
        if abs(current - interval) > 5:
            scheduler.reschedule_job("poll", trigger=IntervalTrigger(seconds=interval))
            logger.info(f"[Daemon] 调整轮询间隔: {int(current)}s → {interval}s")


def main():
    logger.info("=" * 50)
    logger.info("OpenClaw Trading OS Daemon 启动")
    logger.info("=" * 50)

    # 初始估计间隔
    symbols = list(_store.get_all_watched_symbols().keys())
    initial_interval = get_poll_interval(symbols) if symbols else 120
    logger.info(f"[Daemon] 初始轮询间隔: {initial_interval}s，自选 {len(symbols)} 只")

    scheduler.add_job(
        dynamic_poll,
        trigger=IntervalTrigger(seconds=initial_interval),
        id="poll",
        next_run_time=None,  # 不立即执行，等待第一个 interval
        max_instances=1,
        coalesce=True,
    )

    # 立刻执行一次（不等待第一个间隔）
    import threading
    threading.Thread(target=dynamic_poll, daemon=True).start()

    def _shutdown(sig, frame):
        logger.info("[Daemon] 收到停止信号，正在关闭...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("[Daemon] 调度器已启动，按 Ctrl+C 停止")
    scheduler.start()


if __name__ == "__main__":
    main()
