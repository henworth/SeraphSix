#!/usr/bin/env python3
# import json
import logging
import os
import pickle
# import pika
import redis
import requests
import secrets

from flask import Flask, redirect, render_template, request, session, url_for
from flask_kvsession import KVSessionExtension
from requests_oauth2 import OAuth2, OAuth2BearerToken
from seraphsix.constants import LOG_FORMAT_MSG, LOG_FORMAT_TIME
from simplekv.memory.redisstore import RedisStore

log = logging.getLogger()
log.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter(fmt=LOG_FORMAT_MSG, datefmt=LOG_FORMAT_TIME)
handler.setFormatter(formatter)
log.addHandler(handler)

app = Flask(__name__)
app.secret_key = secrets.os.urandom(20)

red = redis.from_url(os.environ.get('REDIS_URL'))

store = RedisStore(red)
KVSessionExtension(store, app)


class BungieClient(OAuth2):
    site = 'https://www.bungie.net'
    authorization_url = '/en/oauth/authorize/'
    token_url = '/platform/app/oauth/token/'


bungie_auth = BungieClient(
    client_id=os.environ.get('BUNGIE_CLIENT_ID'),
    client_secret=os.environ.get('BUNGIE_CLIENT_SECRET'),
    redirect_uri=f"https://{os.environ.get('BUNGIE_REDIRECT_HOST')}/oauth/callback"
)


@app.route('/')
def index():
    session['code'] = request.args.get('code')

    if not session.get('access_token'):
        log.debug(f"No access_token found in session, redirecting to /oauth, {session}")
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
        log.exception(f"/: Failed to publish state info to redis: {user_info} {session}")
        return render_template('message.html', message="Something went wrong.")
    return render_template('redirect.html', site=BungieClient.site, message="Success!")


@app.route('/oauth')
def oauth_index():
    session['state'] = request.args.get('state')

    if not session.get('access_token'):
        log.debug(f"No access_token found in session, redirecting to /oauth/callback, {session}")
        return redirect(
            url_for('oauth_callback')
        )

    with requests.Session() as s:
        s.auth = OAuth2BearerToken(session['access_token'])
        s.headers.update({'X-API-KEY': os.environ.get('BUNGIE_API_KEY')})
        r = s.get(f"{BungieClient.site}/platform/User/GetMembershipsForCurrentUser/")

    r.raise_for_status()
    log.debug(f"/oauth: {session} {request.args}")
    return redirect('/')


@app.route('/oauth/callback')
def oauth_callback():
    code = request.args.get('code')
    error = request.args.get('error')

    if error:
        log.error(repr(error))
        return render_template('message.html', message="Something went wrong.")

    if not code:
        log.debug(f"No code found, redirecting to bungie, {session}")
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
    log.debug(f"/oauth/callback: {session} {request.args}")
    return redirect(url_for('index'))


@app.route('/the100webhook/<int:guild_id>/slack', methods=['POST'])
def the100_webhook(guild_id):
    data = request.get_json(force=True)
    log.info(f"{guild_id} {data}")

    # try:
    #     params = pika.URLParameters(os.environ.get('CLOUDAMQP_URL'))
    #     connection = pika.BlockingConnection(params)
    #     channel = connection.channel()
    #     channel.queue_declare(queue=str(guild_id))
    #     channel.basic_publish(
    #         '',
    #         str(guild_id),
    #         json.dumps(data),
    #         pika.BasicProperties(content_type='application/json', delivery_mode=1)
    #     )
    #     connection.close()
    # except Exception:
    #     log.exception(f"/the100webhook: Failed to publish the100 info to rabbitmq: {guild_id} {data}")
    #     return render_template('message.html', message='Something went wrong.')
    return render_template('message.html', message="Success!")


if __name__ == '__main__':
    app.run(debug=True, ssl_context='adhoc')
