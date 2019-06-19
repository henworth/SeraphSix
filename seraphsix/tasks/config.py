import os


def load_config():
    return {
        'bungie': {
            'api_key': os.environ.get('BUNGIE_API_KEY'),
            'client_id': os.environ.get('BUNGIE_CLIENT_ID'),
            'client_secret': os.environ.get('BUNGIE_CLIENT_SECRET'),
            'redirect_host': os.environ.get('BUNGIE_REDIRECT_HOST')
        },
        'database_url': os.environ.get('DATABASE_URL'),
        'discord_api_key': os.environ.get('DISCORD_API_KEY'),
        # 'iron_cache': {
        #     'project_id': os.environ.get('IRON_CACHE_PROJECT_ID'),
        #     'token': os.environ.get('IRON_CACHE_TOKEN')
        # },
        'redis_url': os.environ.get('REDIS_URL'),
        'the100': {
            'api_key': os.environ.get('THE100_API_KEY'),
            'base_url': os.environ.get('THE100_API_URL'),
        },
        'twitter': {
            'consumer_key': os.environ.get('TWITTER_CONSUMER_KEY'),
            'consumer_secret': os.environ.get('TWITTER_CONSUMER_SECRET'),
            'access_token': os.environ.get('TWITTER_ACCESS_TOKEN'),
            'access_token_secret': os.environ.get('TWITTER_ACCESS_TOKEN_SECRET')
        }
    }
