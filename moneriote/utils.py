import os
import configparser
import sys
import random
from datetime import datetime

import requests


def banner():
    header = """
  \033[92m• ▌ ▄ ·.        ▐ ▄ ▄▄▄ .▄▄▄  ▪        ▄▄▄▄▄▄▄▄ .
  ·██ ▐███▪▪     •█▌▐█▀▄.▀·▀▄ █·██ ▪     •██  ▀▄.▀·
  ▐█ ▌▐▌▐█· ▄█▀▄ ▐█▐▐▌▐▀▀▪▄▐▀▀▄ ▐█· ▄█▀▄  ▐█.▪▐▀▀▪▄
  ██ ██▌▐█▌▐█▌.▐▌██▐█▌▐█▄▄▌▐█•█▌▐█▌▐█▌.▐▌ ▐█▌·▐█▄▄▌
  ▀▀  █▪▀▀▀ ▀█▄▀▪▀▀ █▪ ▀▀▀ .▀  ▀▀▀▀ ▀█▄▀▪ ▀▀▀  ▀▀▀  

    @skftn @Lafudoci @gingeropolous @connorw600
 \033[0m
    """.strip()
    print(header)


def log_err(msg, fatal=False):
    now = datetime.now()
    print('\033[91m[%s]\033[0m %s' % (now.strftime("%Y-%m-%d %H:%M"), msg))

    if fatal:
        sys.exit()


def log_msg(msg):
    now = datetime.now()
    print('\033[92m[%s]\033[0m %s' % (now.strftime("%Y-%m-%d %H:%M"), msg))


def random_user_agent():
    return random.choice([
        'Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:24.0) Gecko/20100101 Firefox/24.0',
        'Mozilla/4.0 (compatible; MSIE 9.0; Windows NT 6.1)',
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:40.0) Gecko/20100101 Firefox/40.1',
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:54.0) Gecko/20100101 Firefox/54.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.113 Safari/537.36',
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:46.0) Gecko/20100101 Firefox/46.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/601.7.7 (KHTML, like Gecko) Version/9.1.2 Safari/601.7.7',
        'Mozilla/5.0 (Windows NT 6.3; WOW64; Trident/7.0; rv:11.0) like Gecko'
    ])


def make_json_request(url, headers=None, method='GET', verbose=True, **kwargs):
    if verbose:
        log_msg("%s: %s" % (method, url))

    kwargs.setdefault('verify', True)
    kwargs.setdefault('timeout', 5)
    kwargs.setdefault('headers', {
        'User-Agent': random_user_agent()
    })

    if headers:
        kwargs['headers'] = headers

    try:
        _method = getattr(requests, method.lower())
        if not _method:
            raise Exception("Unknown method \'%s\'" % method)
    except Exception as ex:
        if verbose:
            log_err(str(ex))
        raise

    try:
        resp = _method(url=url, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except Exception as ex:
        if verbose:
            log_err("Error (%s): %s" % (url, str(ex)))


def parse_ini(fn):
    if not os.path.isfile(fn):
        log_err("%s missing" % fn, fatal=True)

    config = configparser.ConfigParser()
    config.read(fn)

    def try_cast(val):
        if val.isdigit():
            return int(val)
        if val.lower() in ['true', 'false']:
            return bool(val)
        return val

    md = {k: try_cast(v) for k, v in config._sections.get('MoneroDaemon', {}).items()}
    dns = {k: try_cast(v) for k, v in config._sections.get('DNS', {}).items()}
    ban = {k: try_cast(v) for k, v in config._sections.get('BanList', {}).items()}
    return md, dns, ban


def parse_ban_list(path):
    if not os.path.isfile(path):
        log_err("%s missing" % path, fatal=True)
    ban_list = []
    with open(os.path.join(path), 'r') as f:
        for line in f:
            ban_list.append(line.strip())
    return ban_list