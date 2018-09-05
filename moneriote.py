import sys
import json
import re
import os
import subprocess
import random
import configparser
import time
from functools import partial
from multiprocessing import Pool, freeze_support
from subprocess import Popen
from datetime import datetime


PATH_CACHE = 'cached_nodes.json'


def banner():
    header = """
\033[92m• ▌ ▄ ·.        ▐ ▄ ▄▄▄ .▄▄▄  ▪        ▄▄▄▄▄▄▄▄ .
·██ ▐███▪▪     •█▌▐█▀▄.▀·▀▄ █·██ ▪     •██  ▀▄.▀·
▐█ ▌▐▌▐█· ▄█▀▄ ▐█▐▐▌▐▀▀▪▄▐▀▀▄ ▐█· ▄█▀▄  ▐█.▪▐▀▀▪▄
██ ██▌▐█▌▐█▌.▐▌██▐█▌▐█▄▄▌▐█•█▌▐█▌▐█▌.▐▌ ▐█▌·▐█▄▄▌
▀▀  █▪▀▀▀ ▀█▄▀▪▀▀ █▪ ▀▀▀ .▀  ▀▀▀▀ ▀█▄▀▪ ▀▀▀  ▀▀▀  

 @skftn / dsc
 @Lafudoci
 @gingeropolous 
 @connorw600
 \033[0m
    """.strip()
    print(header)


def log_err(msg):
    now = datetime.now()
    print('\033[91m[%s]\033[0m %s' % (now.strftime("%Y-%m-%d %H:%M"), msg))


def log_msg(msg):
    now = datetime.now()
    print('\033[92m[%s]\033[0m %s' % (now.strftime("%Y-%m-%d %H:%M"), msg))


if sys.version_info[0] != 3 or sys.version_info[1] < 3.5:
    log_err("please run with python >= 3.5")
    sys.exit()

try:
    import requests
except ImportError:
    log_err("please install requests: pip install requests")
    sys.exit()


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


def make_json_request(url, timeout=10, verbose=True, **kwargs):
    headers = {
        'User-Agent': random_user_agent()
    }

    try:
        resp = requests.get(url, headers=headers, timeout=timeout, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except Exception as ex:
        if verbose:
            log_err("Error fetching url: %s" % url)
        raise


class RpcNodeList:
    def __init__(self):
        self.nodes = []
        self._addresses = []

    @classmethod
    def from_list(cls, nodes):
        self = cls()
        for node in nodes:
            self.append(node)
        return self

    def append(self, node):
        if node.address not in self._addresses:
            self.nodes.append(node)
            self._addresses.append(node.address)

    def valid(self, valid=True):
        return RpcNodeList.from_list([
            node for node in self.nodes if node.valid is valid])

    def valid_cf(self, valid=True):
        return RpcNodeList.from_list([
            node for node in self.nodes if node.valid is valid and isinstance(node.cf_id, str)])

    def shuffle(self):
        random.shuffle(self.nodes)

    def __iter__(self):
        return iter(self.nodes)

    def __contains__(self, address):
        return address in self._addresses

    def __add__(self, node_list):
        for node in node_list:
            self.append(node)
        return self

    def __len__(self):
        return len(self.nodes)

    def cache_write(self):
        """Writes a cache file of valid nodes"""
        log_msg('Writing \'%s\'' % PATH_CACHE)
        data = []

        for node in self.nodes:
            if node.valid:
                data.append({'address': node.address, 'port': node.port})
        try:
            f = open(PATH_CACHE, 'w')
            f.write(json.dumps(data, indent=4))
            f.close()
        except Exception as ex:
            log_err('Writing \'%s\' failed' % PATH_CACHE)
            raise
        log_msg('Written \'%s\' with %d nodes' % (PATH_CACHE, len(data)))

    @staticmethod
    def cache_read(path):
        """
        Reads nodes from the nodes cache file.
        :return: List of RpcNode objects
        """
        log_msg('Reading \'%s\'' % path)

        try:
            f = open(path, 'r')
            blob = json.loads(f.read())
            f.close()
        except Exception as ex:
            log_err('Reading \'%s\' failed' % path)
            return RpcNodeList()

        if not isinstance(blob, list):
            return RpcNodeList()

        nodes = RpcNodeList()
        for node in blob:
            if 'address' in node:
                nodes.append(RpcNode(**node))

        log_msg('Loaded %d nodes from \'%s\'' % (len(nodes), path))
        return nodes


class RpcNode:
    def __init__(self, address: str, cf_id=None, port=18089):
        """
        :param address: ip
        :param cf_id: active on cloudflare as an A record
        """
        self.address = address
        self.port = port
        self.cf_id = cf_id
        self._acceptableBlockOffset = 3
        self.valid = False

    @staticmethod
    def is_valid(current_blockheight, obj):
        # Scans the current node to see if the RPC port is available and is within the accepted range
        url = 'http://%s:%d/' % (obj.address, obj.port)
        url = '%s%s' % (url, 'getheight')

        try:
            blob = make_json_request(url, verbose=False, timeout=2)
        except Exception as ex:
            return obj

        if not isinstance(blob.get('height', ''), int):
            return obj

        height = blob.get('height')
        block_height_diff = height - current_blockheight

        # Check if the node we're checking is up to date (with a little buffer)
        if obj._acceptableBlockOffset >= block_height_diff >= (obj._acceptableBlockOffset * -1):
            obj.valid = True
        return obj


class Moneriote:
    def __init__(self,
                 cf_domain_name: str,
                 cf_subdomain_name: str,
                 cf_dns_api_key: str, cf_dns_api_email: str,
                 cf_max_records: int = 5,
                 md_address: str = '127.0.0.1',
                 md_port: int = 18082,
                 md_auth: str = 'not:used',
                 md_path: str = 'monerod.exe',
                 md_height_discovery_method: str = 'xmrchain'):
        """See config.ini for documentation on the params."""
        self.md_path = md_path
        self.md_daemon_addr = md_address
        self.md_daemon_port = md_port
        self.md_daemon_auth = md_auth
        if md_height_discovery_method not in ['xmrchain', 'monerod', 'both']:
            log_err('bad height_discovery_method option')
            sys.exit()
        self.md_height_discovery_method = md_height_discovery_method

        self.cf_api_base = 'https://api.cloudflare.com/client/v4/zones'

        # zone_id will be detected via Cloudflare API
        self.cf_zone_id = None
        self.cf_dns_api_key = cf_dns_api_key
        self.cf_dns_api_email = cf_dns_api_email

        # node
        self.cf_subdomain_name = cf_subdomain_name

        # example.com
        self.cf_domain_name = cf_domain_name

        # node.example.com
        self.cf_fulldomain_name = '%s.%s' % (cf_subdomain_name, cf_domain_name)

        # the maximum amount of A records to add
        self.cf_max_records = cf_max_records
        self._cf_headers = {
            'Content-Type': 'application/json',
            'X-Auth-Email': self.cf_dns_api_email,
            'X-Auth-Key': self.cf_dns_api_key,
            'User-Agent': random_user_agent()
        }

        # how many servers we should scan at once
        self._concurrent_scans = 20
        # 10 minutes
        self._loop_interval = 60 * 10
        # default Monero RPC port
        self._m_rpc_port = 18089
        self._blockchain_height = None

        if not os.path.isfile(self._path_nodes_cache):
            log_msg("Auto creating \'%s\'" % self._path_nodes_cache)
            f = open(self._path_nodes_cache, 'a')
            f.write('[]')
            f.close()

    @classmethod
    def from_config(cls):
        if not os.path.isfile('config.ini'):
            log_err("config.ini missing")
            sys.exit()

        config = configparser.ConfigParser()
        config.read('config.ini')

        def try_cast(val):
            if val.isdigit():
                return int(val)
            if val.lower() in ['true', 'false']:
                return bool(val)
            return val

        cfg_monero = {'md_%s' % k: try_cast(v) for k, v in config._sections.get('MoneroDaemon', {}).items()}
        cfg_cloudflare = {'cf_%s' % k: try_cast(v) for k, v in config._sections.get('cloudflareAPI', {}).items()}
        return cls(**{**cfg_cloudflare, **cfg_monero})

    def _daemon_command(self, cmd: str):
        if not os.path.exists(self.md_path):
            log_err("monerod not found in path \'%s\'" % self.md_path)
            return

        log_msg("Spawning daemon; executing command \'%s\'" % cmd)

        # build proc args
        args = [
            '--rpc-bind-ip', self.md_daemon_addr,
            '--rpc-bind-port', str(self.md_daemon_port),
        ]
        if self.md_daemon_auth:
            args.extend(['--rpc-login', self.md_daemon_auth])
        args.append(cmd)

        try:
            process = Popen([self.md_path, *args],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            universal_newlines=True, bufsize=1)
            output, err = process.communicate(timeout=10)
            return output
        except Exception as ex:
            log_err('Could not spawn \'%s %s\': %s' % (
                self.md_path, ' '.join(args), str(ex)
            ))
            sys.exit()
        finally:
            # cleanup
            process.kill()

    def _cf_request(self, url, method='GET', json=None, data=None, params=None):
        _url = '%s/%s' % (self.cf_api_base, url)
        log_msg("Contacting Cloudflare (%s): %s" % (method, _url))

        try:
            _method = getattr(requests, method.lower())
            if not _method:
                raise Exception("Unknown method \'%s\'" % method)
            kwargs = {
                'verify': True,
                'timeout': 5,
                'headers': self._cf_headers
            }
            if data:
                kwargs['data'] = data
            elif params:
                kwargs['params'] = params
            elif json:
                kwargs['json'] = json

            resp = _method(url=_url, **kwargs)
            resp.raise_for_status()

            data = resp.json()
            assert data.get('success') is True
            return data.get('result')
        except Exception as ex:
            log_err("Error contacting Cloudflare (%s): %s" % (url, str(ex)))

    def monerod_get_height(self, method='both'):
        """
        Gets the current top block on the chain
        :param method: 'monerod' will use only monerod to fetch the height.
        'xmrchain' will only use xmrchain. 'both' will query both and compare.
        :return:
        """
        md_height = 0
        xmrchain_height = 0

        if method in ['both', 'monerod']:
            output = self._daemon_command(cmd="print_height")
            if isinstance(output, str) and output.startswith('Error') or not output:
                log_err("monerod output: %s" % output)
            elif isinstance(output, str):
                md_height = int(re.sub('[^0-9]', '', output.splitlines()[0]))
                log_msg('monerod height is %d' % md_height)
                if method == 'monerod':
                    return md_height

        if method in ['both', 'xmrchain']:
            max_retries = 5
            retries = 0

            while True:
                if retries > max_retries:
                    log_msg('xmrchain is not available, not even after %d tries.' % max_retries)
                    break

                try:
                    blob = make_json_request(url='https://xmrchain.net/api/networkinfo', timeout=10, verify=True)
                except Exception as ex:
                    log_msg('Fetching xmrchain JSON has failed. Retrying.')
                    retries += 1
                    time.sleep(10)
                    continue

                try:
                    assert blob.get('status') == 'success'
                    xmrchain_height = blob.get('data', {}).get('height')
                    assert isinstance(xmrchain_height, int)
                    log_msg('xmrchain height is %d' % xmrchain_height)
                    break
                except Exception as ex:
                    log_msg('Decoding xmrchain JSON has failed')
                    break

            if method in ['both', 'monerod'] and md_height > 0:
                # compare xmrchain height to our local monerod height. Use whatever is higher.
                if md_height > xmrchain_height:
                    return md_height
                elif xmrchain_height > md_height:
                    log_msg("Using xmrchain height, because it was higher")
                    return xmrchain_height
                else:
                    log_msg("Using monerod height, because it was higher")
                    return md_height

            if xmrchain_height > 0:
                log_msg("Using xmrchain height")
                return xmrchain_height

        log_err("Failed to get blockheight from either monerod or xmrchain. "
                "Please ensure the config.ini option MoneroDaemon->path is correct "
                "or set MoneroDaemon->use_xmr_chain_as_ref to True.")

    def monerod_get_peers(self):
        """Gets the last known peers from monerod"""
        output = self._daemon_command("print_pl")

        regex = r"(gray|white)\s+(\w+)\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{1,5})"
        matches = re.finditer(regex, output)

        nodes = RpcNodeList()
        for i, match in enumerate(matches):
            if match.group(1) == 'white':
                address = match.group(3)
                nodes.append(RpcNode(address=address))

        log_msg('Got peers from RPC: %d node(s)' % len(nodes))
        return nodes

    def scan(self, nodes: RpcNodeList, remove_invalid=False):
        """
        Start threads checking known nodes to see if they're alive.
        :param nodes:
        :param remove_invalid: only return valid nodes when set to True
        :return: valid nodes
        """
        if len(nodes) == 0:
            return nodes

        now = datetime.now()
        log_msg('Scanning %d node(s) on port %d. This can take several minutes. Let it run.' % (
            len(nodes), self._m_rpc_port))

        pool = Pool(processes=self._concurrent_scans)
        nodes = RpcNodeList.from_list(pool.map(partial(RpcNode.is_valid, self._blockchain_height), nodes))
        pool.close()
        pool.join()

        log_msg('Scanning %d node(s) done after %d seconds, found %d valid' % (
            len(nodes), (datetime.now() - now).total_seconds(), len(nodes.valid(valid=True))))

        if remove_invalid:
            nodes = nodes.valid(valid=True)
        return nodes

    def load_nodes(self):
        # Verify cached nodes
        nodes = RpcNodeList.cache_read(PATH_CACHE)
        nodes = self.scan(nodes, remove_invalid=True)

        # We have enough valid nodes to fill Cloudflare
        if len(nodes) >= self.cf_max_records:
            nodes.cache_write()
            return nodes

        # Ask monerod for more peers and verify
        nodes += self.scan(self.monerod_get_peers(), remove_invalid=True)
        nodes.cache_write()
        return nodes

    def loop(self):
        # get & set the current blockheight
        height = self.monerod_get_height(method=self.md_height_discovery_method)
        if not height or not isinstance(height, int):
            log_err("Unable to fetch the current blockchain height")
            return

        self._blockchain_height = height

        # Get the correct zone
        if not self.cf_zone_id:
            log_msg('Determining zone_id; looking for \'%s\'' % self.cf_domain_name)
            zones = self._cf_request(url='')
            try:
                self.cf_zone_id = next(zone.get('id') for zone in zones if zone.get('name') == self.cf_domain_name)
            except StopIteration:
                log_err('could not determine zone_id. Is your Cloudflare domain correct?')
                sys.exit()
            log_msg('Cloudflare zone_id \'%s\' matched to \'%s\'' % (self.cf_zone_id, self.cf_domain_name))

        # Fetch existing A records from Cloudflare
        nodes = RpcNodeList()

        log_msg('Fetching existing record(s) (%s.%s)' % (self.cf_subdomain_name, self.cf_domain_name))
        for record in self._cf_request('%s/dns_records/' % self.cf_zone_id):
            # filter on A records / subdomain
            if record.get('type') == 'A' and record.get('name') == self.cf_fulldomain_name:
                node = RpcNode(address=record.get('content'),
                               cf_id=record.get('id'),
                               port=self._m_rpc_port)
                nodes.append(node)
        log_msg("Found %d existing record(s) on Cloudflare" % len(nodes))

        # Get nodes from cache / monerod
        nodes += self.load_nodes()

        # Shuffle. Add new records. Stop at max.
        nodes.shuffle()

        # @TODO: smart-insert cloudflare - check exisitng A

        i = 0
        for node in nodes:
            if i >= self.cf_max_records:
                break
            self.cf_add_record(node)
            i += 1

        # If we have room in Cloudflare for records, we need to discover nodes
        # cf_add_count = self.cf_max_records - len(nodes_cf)
        # if cf_add_count <= 0:
        #     log_msg("No need to add more Cloudflare records")
        #     return
        # >>> sorted([{'a': True}, {'a': False}, {'a': False}], key=lambda k: k['a'])
        # alle false eerst

    def cf_add_record(self, node: RpcNode):
        log_msg('Cloudflare record insertion: %s' % node.address)

        try:
            url = '%s/dns_records' % self.cf_zone_id
            blob = self._cf_request(url=url, method='POST', json={
                'name': self.cf_subdomain_name,
                'content': node.address,
                'type': 'A'
            })
        except Exception as ex:
            log_err("Cloudflare record (%s) insertion failed: %s" % (node.address, str(ex)))

    def cf_delete_record(self, node: RpcNode):
        # Delete DNS Record
        log_msg('Cloudflare record deletion: %s' % node.address)
        url = '%s/dns_records/%s' % (self.cf_zone_id, node.cf_id)
        try:
            url = '%s/dns_records/%s' % (self.cf_zone_id, node.cf_id)
            blob = self._cf_request(url=url, method='DELETE')
        except Exception as ex:
            log_err("Cloudflare record (%s) deletion failed: %s" % (node.address, str(ex)))


if __name__ == '__main__':
    banner()
    freeze_support()
    mon = Moneriote.from_config()

    while True:
        mon.loop()
        log_msg("Sleeping %d seconds" % mon._loop_interval)
        time.sleep(mon._loop_interval)
