# pylama:ignore=E731
import aioredis
import logging.config
import msgpack

from arq import Worker
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
        api_key=config.bungie.api_key,
        client_id=config.bungie.client_id,
        client_secret=config.bungie.client_secret,
    )

    database = Database(config.database_url)
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
        store_member_history, store_last_active, store_all_games
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = config.arq_redis
    job_serializer = lambda b: msgpack.packb(b, default=encode_datetime, use_bin_type=True)
    job_deserializer = lambda b: msgpack.unpackb(b, object_hook=decode_datetime, raw=False)
    max_jobs = ARQ_MAX_JOBS
    job_timeout = ARQ_JOB_TIMEOUT


if __name__ == '__main__':
    logging.config.dictConfig(log_config())
    worker = Worker(**get_kwargs(WorkerSettings))
    worker.run()