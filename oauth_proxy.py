#!/usr/bin/env python3
import json
import logging
import os
import pickle
import redis
import requests
import secrets

from flask import Flask, redirect, render_template, request, session
from requests_oauth2 import OAuth2, OAuth2BearerToken
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = secrets.os.urandom(20)

logging.basicConfig(level=logging.INFO)


class BungieClient(OAuth2):
    site = 'https://www.bungie.net'
    authorization_url = '/en/oauth/authorize/'
    token_url = '/platform/app/oauth/token/'


def config_loader(filename='config.json'):
    config = None
    try:
        with open(filename, encoding='utf-8', mode='r') as f:
            config = json.load(f)
    except (FileNotFoundError, json.decoder.JSONDecodeError):
        logging.info("Config file config.json does not exist. Ignoring...")

    if not config or 'bungie' not in config.keys():
        config = {
            'bungie': {
                'api_key': os.environ.get('BUNGIE_API_KEY'),
                'group_id': os.environ.get('GROUP_ID'),
                'client_id': os.environ.get('CLIENT_ID'),
                'client_secret': os.environ.get('CLIENT_SECRET'),
                'redirect_host': os.environ.get('REDIRECT_HOST')
            },
            'redis_url': os.environ.get("REDIS_URL"),
        }
    return config


config = config_loader()

bungie_auth = BungieClient(
    client_id=config['bungie']['client_id'],
    client_secret=config['bungie']['client_secret'],
    redirect_uri=f'https://{config["bungie"]["redirect_host"]}/oauth/callback'
)

red = redis.from_url(config['redis_url'])


@app.route("/")
def index():
    if session.get('access_token'):
        return render_template('redirect.html', site=BungieClient.site, message='Success!')
    else:
        return redirect("/oauth/")


@app.route('/oauth/')
def oauth_index():
    if not session.get('access_token'):
        return redirect('/oauth/callback')
    
    with requests.Session() as s:
        s.auth = OAuth2BearerToken(session['access_token'])
        s.headers.update({'X-API-KEY': config['bungie']['api_key']})
        r = s.get(f'{BungieClient.site}/platform/User/GetMembershipsForCurrentUser/')
    
    r.raise_for_status()
    return redirect('/')


@app.route('/oauth/callback')
def oauth_callback():
    code = request.args.get('code')
    error = request.args.get('error')
    state = request.args.get('discord_id') or secrets.token_urlsafe(24)

    if error:
        return 'error :( {!r}'.format(error)
    
    if not code:
        return redirect(bungie_auth.authorize_url(
            response_type='code',
            state=state
        ))

    data = bungie_auth.get_token(
        code=code,
        grant_type='authorization_code',
    )

    user_info = dict(
        membership_id = data.get('membership_id'),
        access_token = data.get('access_token'),
        refresh_token = data.get('refresh_token')
    )

    pickled_info = pickle.dumps(user_info)
    red.publish(state, pickled_info)
    session['access_token'] = user_info['access_token']
    session['refresh_token'] = user_info['refresh_token']
    return redirect('/')


if __name__ == '__main__':
    app.run(debug=True, ssl_context='adhoc')
