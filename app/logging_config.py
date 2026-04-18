"""集中化 logging 設定。

- request_id_var / user_id_var：ContextVar，由 middleware 設值、logger 讀取
- configure_logging()：app 啟動時呼叫一次，設 sink + format + patcher
"""

import sys
from contextvars import ContextVar

from loguru import logger

from app.config import settings


# 整個 request 生命週期共用的隱形公事包
# middleware 進入時 set，request 結束自動清（ContextVar 本身的機制）
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
user_id_var: ContextVar[int | None] = ContextVar("user_id", default=None)


def _inject_context(record) -> None:
    """每筆 log 自動從 ContextVar 抓 request_id + user_id 塞進 extra 欄位。"""
    record["extra"]["request_id"] = request_id_var.get()
    record["extra"]["user_id"] = user_id_var.get()


def configure_logging() -> None:
    """App 啟動時呼叫一次。移除 loguru 預設 sink，依 LOG_JSON 切 format。"""
    logger.remove()

    if settings.LOG_JSON:
        # JSON 一行。serialize=True 會把 time / level / message / extra 全部 dump 成 JSON
        logger.add(sys.stdout, serialize=True, level=settings.LOG_LEVEL)
    else:
        logger.add(
            sys.stdout,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> "
                "<level>{level: <8}</level> "
                "<cyan>req={extra[request_id]}</cyan> "
                "<magenta>user={extra[user_id]}</magenta> "
                "<level>{message}</level>"
            ),
            level=settings.LOG_LEVEL,
            colorize=True,
        )

    # patcher 會在每筆 record 進 sink 前呼叫，把 ContextVar 內容塞進 extra
    logger.configure(patcher=_inject_context)
