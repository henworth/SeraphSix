#!/usr/bin/env python3
import logging
import logging.config
import pickle
import redis
import requests

from flask import Flask, redirect, render_template, request, session, url_for
from flask_kvsession import KVSessionExtension
from requests_oauth2 import OAuth2, OAuth2BearerToken
from seraphsix.tasks.config import Config, log_config
from simplekv.memory.redisstore import RedisStore

config = Config()
logging.config.dictConfig(log_config())
log = logging.getLogger()

app = Flask(__name__)
app.secret_key = config.flask_app_key
red = redis.from_url(config.redis_url)

store = RedisStore(red)
KVSessionExtension(store, app)


class BungieClient(OAuth2):
    site = 'https://www.bungie.net'
    authorization_url = '/en/oauth/authorize/'
    token_url = '/platform/app/oauth/token/'


bungie_auth = BungieClient(
    client_id=config.bungie.client_id,
    client_secret=config.bungie.client_secret,
    redirect_uri=f'https://{config.bungie.redirect_host}/oauth/callback'
)


@app.route('/')
def index():
    session['code'] = request.args.get('code')

    if not session.get('access_token'):
        log.debug(f'No access_token found in session, redirecting to /oauth, {session}')
        return redirect(
            url_for('oauth_index')
        )

    user_info = dict(
        membership_id=session.get('membership_id'),
        access_token=session.get('access_token'),
        refresh_token=session.get('refresh_token')
    )

    pickled_info = pickle.dumps(user_info)
    try:
        red.publish(session['state'], pickled_info)
    except Exception:
        log.exception(f'/: Failed to publish state info to redis: {user_info} {session}')
        return render_template('message.html', message='Something went wrong.')
    return render_template('redirect.html', site=BungieClient.site, message='Success!')


@app.route('/oauth')
def oauth_index():
    session['state'] = request.args.get('state')

    if not session.get('access_token'):
        log.debug(f'No access_token found in session, redirecting to /oauth/callback, {session}')
        return redirect(
            url_for('oauth_callback')
        )

    with requests.Session() as s:
        s.auth = OAuth2BearerToken(session['access_token'])
        s.headers.update({'X-API-KEY': config.bungie.api_key})
        r = s.get(f'{BungieClient.site}/platform/User/GetMembershipsForCurrentUser/')

    r.raise_for_status()
    log.debug(f'/oauth: {session} {request.args}')
    return redirect('/')


@app.route('/oauth/callback')
def oauth_callback():
    code = request.args.get('code')
    error = request.args.get('error')

    if error:
        log.error(repr(error))
        return render_template('message.html', message='Something went wrong.')

    if not code:
        log.debug(f'No code found, redirecting to bungie, {session}')
        return redirect(bungie_auth.authorize_url(
            response_type='code',
            state=session['state']
        ))

    data = bungie_auth.get_token(
        code=code,
        grant_type='authorization_code',
    )

    session['code'] = code
    session['access_token'] = data.get('access_token')
    session['refresh_token'] = data.get('refresh_token')
    session['membership_id'] = data.get('membership_id')
    log.debug(f'/oauth/callback: {session} {request.args}')
    return redirect(url_for('index'))


@app.route('/the100webhook/<int:guild_id>/slack', methods=['POST'])
def the100_webhook(guild_id):
    data = request.get_json(force=True)
    log.info(f'{guild_id} {data}')
    return render_template('message.html', message='Success!')


if __name__ == '__main__':
    app.run(debug=True, ssl_context='adhoc')
