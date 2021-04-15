# pylama:ignore=E731
import aioredis
import logging.config
import msgpack

from arq import Worker, func
from arq.worker import get_kwargs
from pydest.pydest import Pydest
from seraphsix.constants import ARQ_JOB_TIMEOUT, ARQ_MAX_JOBS
from seraphsix.database import Database
from seraphsix.tasks.activity import (
    get_characters, process_activity, store_member_history, store_last_active, store_all_games
)
from seraphsix.tasks.core import set_cached_members
from seraphsix.tasks.config import Config, log_config
from seraphsix.tasks.parsing import encode_datetime, decode_datetime

config = Config()


async def startup(ctx):
    ctx['destiny'] = Pydest(
        api_key=config.destiny.api_key,
        client_id=config.destiny.client_id,
        client_secret=config.destiny.client_secret,
    )

    database = Database(config.database_url, config.database_conns)
    database.initialize()
    ctx['database'] = database
    ctx['redis_cache'] = await aioredis.create_redis_pool(config.redis_url)
    ctx['redis_jobs'] = ctx['redis']


async def shutdown(ctx):
    await ctx['destiny'].close()
    if 'database' in ctx:
        await ctx['database'].close()
    if 'redis_cache' in ctx:
        ctx['redis_cache'].close()
        await ctx['redis_cache'].wait_closed()


class WorkerSettings:
    functions = [
        set_cached_members, get_characters, process_activity,
        store_member_history, func(store_last_active, keep_result=240),
        store_all_games
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = config.arq_redis
    max_jobs = ARQ_MAX_JOBS
    job_timeout = ARQ_JOB_TIMEOUT

    def job_serializer(b):
        return msgpack.packb(b, default=encode_datetime)

    def job_deserializer(b):
        return msgpack.unpackb(b, object_hook=decode_datetime)


if __name__ == '__main__':
    logging.config.dictConfig(log_config())
    worker = Worker(**get_kwargs(WorkerSettings))
    worker.run()
