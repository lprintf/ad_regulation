import os
import time
from typing import Iterator

import pandas as pd
from facebook_business.adobjects.adreportrun import AdReportRun

from utils.fb_api_flyweight_factory import get_ad_object
from utils.insight_tool import (
    ATOMIC_FIELDS,
    ensure_atomic_insight_df_type,
    get_atomic_metric,
    get_daily_insight,
)

ROOT_DIR = "D:/data/insights_data_1020"


def get_file_path(ad_account_id, date_start, date_stop, root_dir=ROOT_DIR) -> str:
    if ad_account_id[:4] == "act_":
        ad_account_id = ad_account_id[4:]

    file_path = os.path.join(
        root_dir, f"{ad_account_id}_{date_start}_{date_stop}.feather"
    )
    return file_path


async def get_insight_tasks(
    ad_account_ids: list[str],
    level="ad",
    fields=[
        "ad_id",
        # "account_id",
        *ATOMIC_FIELDS,
    ],
    since="2022-09-14",
    until="2025-10-13",
    sort="",
    limit=100000,
    root_dir=ROOT_DIR,
):
    """用于异步获取数据拉取任务"""
    task_list = []
    for account_id in ad_account_ids:
        # 如果文件已经存在，则跳过
        path = get_file_path(account_id, since, until, root_dir=root_dir)
        if os.path.exists(path):
            print(f"File {path} already exists, skipping...")
            continue

        ad_object = await get_ad_object(account_id, account_id)

        task = get_daily_insight(
            ad_object,
            level=level,
            fields=fields,
            since=since,
            until=until,
            sort=sort,
            limit=limit,
            is_async=True,
        )
        task_list.append(task)
    return task_list


async def get_insight(
    ad_account_id: str,
    level="ad",
    fields=[
        "ad_id",
        # "account_id",
        *ATOMIC_FIELDS,
    ],
    since="2022-09-14",
    until="2025-10-13",
    sort="",
    limit=100000,
):
    """用于同步获取数据拉取任务"""
    account_id = ad_account_id
    # 如果文件已经存在，则跳过
    ad_object = await get_ad_object(account_id, account_id)

    insight = get_daily_insight(
        ad_object,
        level=level,
        fields=fields,
        since=since,
        until=until,
        sort=sort,
        limit=limit,
    )
    return insight


def insight_to_df(insight: list) -> pd.DataFrame:
    df = pd.DataFrame(
        (
            {
                "ad_id": _["ad_id"],
                # "account_id": _["account_id"],
                "date_start": _["date_start"],
                **get_atomic_metric(_),
            }
            for _ in insight
        )
    )
    df = ensure_atomic_insight_df_type(df)
    return df


def _extract_insights_data(task: Iterator, root_dir=ROOT_DIR):
    """
    Extract insights data from completed tasks and convert to pandas DataFrames, save to disk, and return the file path.
    """

    insights_cursor = task.get_insights()
    df = insight_to_df(insights_cursor)

    file_path = get_file_path(
        task[task.Field.account_id],
        task[task.Field.date_start],
        task[task.Field.date_stop],
        root_dir=root_dir,
    )
    df.to_feather(file_path)
    return file_path


def await_async_tasks(
    task_list: list[AdReportRun],
    max_attempts=200,
    sleep_interval=60,
    root_dir=ROOT_DIR,
):
    """
    Monitor asynchronous Facebook API tasks until completion or failure.
    If a task completes successfully, its data will be saved to disk.

    Args:
        task_list: List of async tasks to monitor
        max_attempts: Maximum number of monitoring attempts (default: 20)
        sleep_interval: Time to wait between checks in seconds (default: 60)

    Returns:
        tuple: (completed_tasks, failed_tasks)
    """
    running_task = task_list.copy()
    completed_task = []
    failed_task = []

    for _ in range(max_attempts):
        for i in range(len(running_task) - 1, -1, -1):
            task = running_task[i]
            task.api_get()
            status = task[AdReportRun.Field.async_status]
            if status == "Job Completed":
                running_task.pop(i)
                completed_task.append(task)
                print("Task Complete:")
                print({**task})
                _extract_insights_data(task, root_dir)
            elif status in ["Job Failed", "Job Skipped"]:
                print("Task Failed:")
                print({**task})
                failed_task.append(task)
            else:
                async_percent_completion = task[
                    AdReportRun.Field.async_percent_completion
                ]
                print(
                    f"Task {task[AdReportRun.Field.account_id]} in progress: {async_percent_completion}%"
                )
        if len(running_task) == 0:
            break
        print(f"Remaining tasks: {len(running_task)}")
        time.sleep(sleep_interval)

    return completed_task, failed_task


if __name__ == "__main__":
    import asyncio

    from config import (
        MONGO_INITDB_ROOT_PASSWORD,
        MONGO_INITDB_ROOT_USERNAME,
        MONGODB_DB_NAME,
        MONGODB_PORT,
    )
    from utils.db import close_db, init_db

    mongo_url = f"mongodb://{MONGO_INITDB_ROOT_USERNAME}:{MONGO_INITDB_ROOT_PASSWORD}@{"localhost"}:{MONGODB_PORT}/{MONGODB_DB_NAME}?authSource=admin"

    async def main():
        await init_db(mongo_url)
        ad_account_ids = [
            "act_790736016835429",
            "act_1243925423619499",
        ]
        yesterdays = pd.Timestamp.now() - pd.Timedelta(days=1)
        until = yesterdays.strftime("%Y-%m-%d")
        since = (yesterdays - pd.Timedelta(days=1125)).strftime("%Y-%m-%d")
        since = (yesterdays - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
        # print(f"Since: {since}, Until: {until}")
        # task_list = await get_insight_tasks(ad_account_ids, since=since, until=until)
        # completed_task, failed_task = await_async_tasks(task_list)
        # print(f"Completed tasks: {completed_task}")
        # print(f"Failed tasks: {failed_task}")

        insight = await get_insight(ad_account_ids[1], since=since, until=until)
        df = insight_to_df(insight)
        path = f"{ad_account_ids[1]}_{since}_{until}.feather"
        df.to_feather(path)
        print(f"Saved to {path}")

        await close_db()

    asyncio.run(main())
