import sys
import re
import os
import subprocess
import time
from functools import partial
from multiprocessing import Pool
from subprocess import Popen
from datetime import datetime

from moneriote import PATH_CACHE, CONFIG
from moneriote.dns import DnsProvider
from moneriote.rpc import RpcNode, RpcNodeList
from moneriote.utils import log_msg, log_err, make_json_request, banner


if sys.version_info[0] != 3 or sys.version_info[1] < 3.5:
    log_err("please run with python >= 3.5", fatal=True)

try:
    import requests
except ImportError:
    log_err("please install requests: pip install requests", fatal=True)


class Moneriote:
    def __init__(self, dns_provider: DnsProvider, md_address: str = '127.0.0.1', md_port: int = 18081,
                 md_auth: str = 'not:used', md_path: str = 'monerod.exe',
                 md_height_discovery_method: str = 'xmrchain'):
        self.dns_provider = dns_provider

        self.md_path = md_path
        self.md_daemon_addr = md_address
        self.md_daemon_port = md_port
        self.md_daemon_auth = md_auth
        if md_height_discovery_method not in ['xmrchain', 'monerod', 'compare', 'moneroblocks']:
            log_err('bad height_discovery_method option', fatal=True)
        self.md_height_discovery_method = md_height_discovery_method

        # default Monero RPC port
        self._m_rpc_port = 18089
        self._blockchain_height = None

        if not os.path.isfile(PATH_CACHE):
            log_msg("Auto creating \'%s\'" % PATH_CACHE)
            f = open(PATH_CACHE, 'a')
            f.write('[]')
            f.close()

        self.monerod_check()

    def main(self):
        # get & set the current blockheight
        height = self.monerod_get_height(method=self.md_height_discovery_method)
        if not height or not isinstance(height, int):
            log_err("Unable to fetch the current blockchain height")
            return
        self._blockchain_height = height

        nodes = RpcNodeList()
        nodes += RpcNodeList.cache_read(PATH_CACHE)  # from `cached_nodes.json`
        if nodes:
            nodes = self.scan(nodes, remove_invalid=True)

        if len(nodes.nodes) <= 2:
            peers = self.monerod_get_peers()  # from monerod
            nodes += self.scan(peers, remove_invalid=True)

        if nodes.nodes:
            nodes.cache_write()

        nodes.shuffle()
        inserts = nodes.nodes[:self.dns_provider.max_records]
        dns_nodes = self.dns_provider.get_records()

        # insert new records
        for node in inserts:
            if node.address not in dns_nodes:
                self.dns_provider.add_record(node)

        # remove old records
        for i, node in enumerate(dns_nodes):
            if node.address not in nodes or i >= self.dns_provider.max_records:
                self.dns_provider.delete_record(node)

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

        pool = Pool(processes=CONFIG['concurrent_scans'])
        nodes = RpcNodeList.from_list(pool.map(partial(RpcNode.is_valid, self._blockchain_height), nodes))
        pool.close()
        pool.join()

        log_msg('Scanning %d node(s) done after %d seconds, found %d valid' % (
            len(nodes), (datetime.now() - now).total_seconds(), len(nodes.valid(valid=True))))

        if remove_invalid:
            nodes = nodes.valid(valid=True)

        return nodes

    def monerod_check(self):
        url = 'http://%s:%d' % (self.md_daemon_addr, self.md_daemon_port)

        try:
            resp = requests.get(url, timeout=2)
            assert resp.status_code == 404
            assert resp.headers.get('Server', '').startswith('Epee')
            return True
        except Exception as ex:
            log_err("monerod not reachable: %s" % url, fatal=True)

    def monerod_get_height(self, method='compare'):
        """
        Gets the current top block on the chain
        :param method: 'monerod' will use only monerod to fetch the height.
        'xmrchain' will only use xmrchain. 'both' will query both and compare.
        :return:
        """
        data = {}
        xmrchain_height = 0
        max_retries = 5

        if method == ['compare', 'monerod']:
            output = self._daemon_command(cmd="print_height")
            if isinstance(output, str) and output.startswith('Error') or not output:
                log_err("monerod output: %s" % output)
            elif isinstance(output, str):
                data['md_height'] = int(re.sub('[^0-9]', '', output.splitlines()[0]))
                log_msg('monerod height is %d' % data['md_height'])
                if method == 'monerod':
                    return data['md_height']

        if method in ['compare', 'moneroblocks']:
            retries = 0
            while True:
                if retries > max_retries:
                    break
                try:
                    blob = make_json_request('https://moneroblocks.info/api/get_stats/', timeout=5, verify=True)
                    data['moneroblocks'] = blob.get('height')
                    break
                except Exception as ex:
                    log_msg('Fetching moneroblocks JSON has failed. Retrying.')
                    retries += 1
                    time.sleep(1)

        if method in ['compare', 'xmrchain']:
            retries = 0
            while True:
                if retries > max_retries:
                    break
                try:
                    blob = make_json_request('https://xmrchain.net/api/networkinfo', timeout=5, verify=True)
                    assert blob.get('status') == 'success'
                    data['xmrchain_height'] = blob.get('data', {}).get('height')
                    assert isinstance(data['xmrchain_height'], int)
                    log_msg('xmrchain height is %d' % data['xmrchain_height'])
                    if method == 'xmrchain':
                        return data['xmrchain_height']
                    break
                except Exception as ex:
                    log_msg('Fetching xmrchain JSON has failed. Retrying.')
                    retries += 1
                    time.sleep(1)
                    continue

        if data:
            return max(data.values())
        log_err('Unable to obtain blockheight.')

    def monerod_get_peers(self):
        """Gets the last known peers from monerod"""
        nodes = RpcNodeList()
        output = self._daemon_command("print_pl")
        if not output:
            return nodes

        regex = r"(gray|white)\s+(\w+)\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{1,5})"
        matches = re.finditer(regex, output)

        for i, match in enumerate(matches):
            if match.group(1) != 'white':
                continue

            address = match.group(3)
            nodes.append(RpcNode(address=address))

        log_msg('Got peers from RPC: %d node(s)' % len(nodes))
        return nodes

    def _daemon_command(self, cmd: str):
        if not os.path.exists(self.md_path):
            log_err("monerod not found in path \'%s\'" % self.md_path)
            return

        log_msg("Spawning daemon; executing command \'%s\'" % cmd)

        # build proc args
        args = [
            '--rpc-bind-ip', self.md_daemon_addr,
            '--rpc-bind-port', str(18081),
        ]
        if self.md_daemon_auth:
            args.extend(['--rpc-login', self.md_daemon_auth])
        args.append(cmd)

        try:
            process = Popen([self.md_path, *args],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            universal_newlines=True, bufsize=1)
            output, err = process.communicate(timeout=10)
            if not output:
                log_err("No output from monerod")
            return output
        except Exception as ex:
            log_err('Could not spawn \'%s %s\': %s' % (
                self.md_path, ' '.join(args), str(ex)
            ))
            sys.exit()
        finally:
            # cleanup
            process.kill()
