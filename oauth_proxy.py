#!/usr/bin/env python3
import logging
import os
import pickle
import redis
import requests
import secrets

from flask import Flask, redirect, render_template, request, session, url_for
from requests_oauth2 import OAuth2, OAuth2BearerToken

app = Flask(__name__)
app.secret_key = secrets.os.urandom(20)

logging.basicConfig(level=logging.INFO)


class BungieClient(OAuth2):
    site = 'https://www.bungie.net'
    authorization_url = '/en/oauth/authorize/'
    token_url = '/platform/app/oauth/token/'


bungie_auth = BungieClient(
    client_id=os.environ.get('BUNGIE_CLIENT_ID'),
    client_secret=os.environ.get('BUNGIE_CLIENT_SECRET'),
    redirect_uri=f'https://{os.environ.get("BUNGIE_REDIRECT_HOST")}/oauth/callback'
)

red = redis.from_url(os.environ.get('REDIS_URL'))


@app.route('/')
def index():
    if not session.get('access_token'):
        return redirect('/oauth/')

    user_info = dict(
        membership_id=session.get('membership_id'),
        access_token=session.get('access_token'),
        refresh_token=session.get('refresh_token')
    )

    pickled_info = pickle.dumps(user_info)
    red.publish(session.get('state'), pickled_info)
    return render_template('redirect.html', site=BungieClient.site, message='Success!')


@app.route('/oauth/')
def oauth_index():
    if not session.get('access_token'):
        return redirect(url_for('oauth_callback', state=request.args.get('state')))

    with requests.Session() as s:
        s.auth = OAuth2BearerToken(session['access_token'])
        s.headers.update({'X-API-KEY': os.environ.get('BUNGIE_API_KEY')})
        r = s.get(
            f'{BungieClient.site}/platform/User/GetMembershipsForCurrentUser/')

    r.raise_for_status()
    return redirect('/')


@app.route('/oauth/callback')
def oauth_callback():
    code = request.args.get('code')
    error = request.args.get('error')
    state = request.args.get('state')

    if error:
        return repr(error)

    if not code:
        return redirect(bungie_auth.authorize_url(
            response_type='code',
            state=state
        ))

    data = bungie_auth.get_token(
        code=code,
        grant_type='authorization_code',
    )

    session['access_token'] = data.get('access_token')
    session['refresh_token'] = data.get('refresh_token')
    session['membership_id'] = data.get('membership_id')
    session['state'] = request.args.get('state')
    return redirect('/')


@app.route('/the100webhook/slack', methods=['POST'])
def the100_webhook():
    logging.info(request.headers)
    logging.info(request.get_data(as_text=True))
    logging.info(request.get_json(force=True))
    return 'Success!'


if __name__ == '__main__':
    app.run(debug=True, ssl_context='adhoc')
