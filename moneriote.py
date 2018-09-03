#!/usr/bin/python3.5
from functools import partial
from multiprocessing import Pool, freeze_support
from subprocess import Popen
from datetime import datetime

import json, re, requests, subprocess, random, configparser, time


class Moneriote:
    def __init__(self, cf_domain_name: str, cf_dns_api_zone: str,
                 cf_dns_api_key: str, cf_dns_api_email: str,
                 md_address: str = '127.0.0.1',
                 md_port: int = 18082,
                 md_auth: str = 'not:used',
                 md_path: str = 'monerod.exe',
                 md_use_xmr_chain_as_ref: bool = True):
        """See config.ini for documentation on the params."""
        self.md_path = md_path
        self.md_daemon_addr = md_address
        self.md_daemon_port = md_port
        self.md_daemon_auth = md_auth
        self.md_use_xmr_chain_as_ref = md_use_xmr_chain_as_ref

        self.cf_domain_name = cf_domain_name
        self.cf_dns_api_zone = cf_dns_api_zone
        self.cf_dns_api_key = cf_dns_api_key
        self.cf_dns_api_email = cf_dns_api_email

        self._cf_headers = {
            'Content-Type': 'application/json',
            'X-Auth-Email': self.cf_dns_api_email,
            'X-Auth-Key': self.cf_dns_api_key
        }

        self._maximumConcurrentScans = 16  # How many servers we should scan at once
        self._acceptableBlockOffset = 3  # How much variance in the block height will be allowed
        self._scanInterval = 10  # N Minutes

        # Default Monero RPC port
        self._m_rpc_port = 18089

        self._currentNodes = []  # store current usable opennodes
        self._dns_record = {}  # store current DNS record

    @classmethod
    def from_config(cls):
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

    @property
    def cf_dns_api_url(self):
        return 'https://api.cloudflare.com/client/v4/zones/%s/dns_records/' % self.cf_dns_api_zone

    def _daemon_command(self, cmd: str):
        Moneriote.log_msg("spawning daemon; executing command \'%s\'" % cmd)

        # build proc args
        args = [
            '--rpc-bind-ip', self.md_daemon_addr,
            '--rpc-bind-port', self.md_daemon_port,
        ]
        if self.md_daemon_auth:
            args.extend(['--rpc-login', self.md_daemon_auth])
        args.append(cmd)

        process = Popen([self.md_path, *args],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        universal_newlines=True, bufsize=1)
        output, err = process.communicate(timeout=10)
        output = output.decode('utf8')

        # cleanup proc
        try:
            process.kill()
            process.communicate()
        except:
            pass
        return output

    def blockchain_height(self):
        """
        Gets the current top block on the chain
        :return: daemon height as int
        """
        daemon_height = None
        ref_height = None

        output = self._daemon_command(cmd="print_height")

        if output.startswith('Error'):
            Moneriote.log_err(output)
        else:
            daemon_height = int(re.sub('[^0-9]', '', output.splitlines()[0]))
            Moneriote.log_msg('Daemon height is %d' % daemon_height)

        # Gets height from xmrchain
        if self.md_use_xmr_chain_as_ref:
            max_retries = 5
            retries = 0

            while True:
                if retries > max_retries:
                    Moneriote.log_err('xmrchain is not available now. Using daemon height...')
                try:
                    resp = requests.get(url='https://xmrchain.net/api/networkinfo', timeout=20)
                    resp.raise_for_status()  # raise on non-200 status
                    blob = json.loads(resp.text)
                except Exception as ex:
                    Moneriote.log_err('Fetching xmrchain JSON has failed')
                    Moneriote.log_err(str(ex))
                    Moneriote.log_err('Retry in 10s ...')
                    retries += 1
                    time.sleep(10)
                    continue

                try:
                    assert blob.get('status') == 'success'
                    ref_height = blob.get('data', {}).get('height')
                    assert ref_height.isdigit()
                    ref_height = int(ref_height)
                    break
                except Exception as ex:
                    Moneriote.log_err('Decoding xmrchain JSON has failed')
                    Moneriote.log_err(str(ex))
                    continue

            Moneriote.log_msg('xmrchain height is %d' % ref_height)

            # Compare block height
            if daemon_height is not None and ref_height > daemon_height:
                Moneriote.log_msg('xmrchain height is higher. Daemon might be lagging. Using xmrchain height.')
                return ref_height
            elif ref_height is None:
                Moneriote.log_err('xmrchain is not available now. Using daemon height.')
        return daemon_height

    def load_nodes(self):
        """Gets the last known peers from the server"""
        nodes = []
        output = self._daemon_command("print_pl")

        regex = r"(gray|white)\s+(\w+)\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{1,5})"
        matches = re.finditer(regex, output)

        for i, match in enumerate(matches):
            if match.group(1) == 'white':
                address = match.group(3)
                if address not in currentNodes and address != '0.0.0.0':
                    nodes.append(address)

        Moneriote.log_msg('Got peers from RPC: %d nodes' % len(nodes))
        return nodes

    def scan_node(self, accepted_height, address):
        """
        Scans the requested address to see if the RPC port is available and is within the accepted range
        :param accepted_height:
        :param address:
        :return:
        """
        url = 'http://%s:%d/getheight' % (address, self._m_rpc_port)

        try:
            resp = requests.get(url, timeout=3)
            resp.raise_for_status()
            blob = json.loads(resp.text)
            assert blob.get('height', '').isdigit()
            height = int(blob.get('height'))
            block_height_diff = height - accepted_height

            # Check if the node we're checking is up to date (with a little buffer)
            if self._acceptableBlockOffset >= block_height_diff >= (self._acceptableBlockOffset * -1):
                return {'address': address, 'valid': True}
        except ValueError as ex:
            Moneriote.log_err("Could not validate JSON for RPC \'%s\': %s" % (url, str(ex)))
        except requests.exceptions.RequestException:
            Moneriote.log_err('Scan node: \'%s\': failed' % url)
        return {'address': address, 'valid': False}

    @staticmethod
    def log_err(msg):
        now = datetime.now()
        print('\033[91m[%s]\033[0m %s' % (now.strftime("%Y-%m-%d %H:%M"), msg))

    @staticmethod
    def log_msg(msg):
        now = datetime.now()
        print('\033[92m[%s]\033[0m %s' % (now.strftime("%Y-%m-%d %H:%M"), msg))


def start_scanning_threads(current_nodes, blockchain_height):
    """Start threads checking known nodes to see if they're alive."""
    global currentNodes

    log_msg('Scanning port ' + str(rpcPort) + ' online & synced (height ' + str(blockchain_height) + ') nodes...')

    pool = Pool(processes=maximumConcurrentScans)
    response = pool.map(partial(scan_node, blockchain_height), current_nodes)

    pool.close()
    pool.join()

    for node in response:
        if node['valid'] is True and node['address'] not in currentNodes:
            currentNodes.append(node['address'])

        if node['valid'] is False and node['address'] in currentNodes:
            currentNodes.remove(node['address'])

    log_msg('After screening: ' + str(len(currentNodes)) + ' nodes')

    try:
        cn = open('current_nodes', 'w')
        cn.write(json.dumps(currentNodes))
        cn.close()
    except (OSError, IOError) as e:
        log_err('Write current_nodes file error:' + e)


"""
    Update our dns records
"""


def update_dns_records():
    if currentNodes.__len__() > 3:
        random_record = random.sample(currentNodes, 3)  # random pick 3 records
        log_msg('Random pick 3 IP for DNS records')
    else:
        random_record = currentNodes  # if less than 3 then use all records
        log_msg('Use all IP for DNS records')

    log_msg('Start building records')

    try:
        res_cf = requests.get(url=dnsApiUrl, params={'name': doaminName, 'per_page': 100}, headers=headers_cf)
        json_cf = json.loads(res_cf.text)
        # log_msg(json_cf)
        if json_cf['success'] == True:
            log_msg('Success When Get DNS List')
            # Create DNS Record
            for node_obj in random_record:
                flag_exist = False
                for list_obj in json_cf['result']:
                    if list_obj['name'] == doaminName and list_obj['content'] == node_obj:
                        flag_exist = True
                        break
                if flag_exist:
                    log_msg(node_obj + ' already exist')
                else:
                    try:
                        res_create = requests.post(url=dnsApiUrl,
                                                   json={'name': doaminName, 'type': 'A', 'content': node_obj},
                                                   headers=headers_cf)
                        json_create = json.loads(res_create.text)
                        if json_create['success'] == True:
                            log_msg(node_obj + ' create record success')
                        else:
                            log_err(node_obj + ' create record fail')
                            log_err(res_create.text)
                    except (requests.exceptions.RequestException, ValueError) as err:
                        log_msg(str(err))
            # Delete DNS Record
            for list_obj in json_cf['result']:
                if list_obj['name'] == doaminName:
                    flag_exist = False
                    for node_obj in random_record:
                        if node_obj == list_obj['content']:
                            flag_exist = True
                            break
                    if not flag_exist:
                        try:
                            res_del = requests.delete(url=dnsApiUrl + list_obj['id'], headers=headers_cf)
                            json_del = json.loads(res_del.text)
                            if json_del['success'] == True:
                                log_msg(list_obj['content'] + ' delete record success')
                            else:
                                log_err(list_obj['content'] + ' delete record fail')
                                log_err(res_del.text)
                        except (requests.exceptions.RequestException, ValueError) as err:
                            log_msg(str(err))
        else:
            log_err('Error When Get DNS List')
    except (requests.exceptions.RequestException, ValueError) as err:
        log_err(str(err))


def check_all_nodes():
    global currentNodes

    try:
        cn = open('current_nodes', 'r')  # read last nodes list from file
        currentNodes = json.loads(cn.read())
        cn.close()
        log_msg('Loaded ' + str(currentNodes.__len__()) + ' nodes in current_nodes.')
    except (OSError, IOError) as e:
        log_msg('File current_nodes was not found, will create new.')

    if currentNodes.__len__() > 0:  # scan current existing nodes
        log_msg('Checking existing nodes...')
        start_scanning_threads(currentNodes, get_blockchain_height())

    log_msg('\nGetting new peers...')  # look for new nodes from daemon
    start_scanning_threads(load_nodes(), get_blockchain_height())

    log_msg('Building DNS records...')  # Build DNS records
    if currentNodes.__len__() > 0:
        update_dns_records()
    else:
        log_err('No available node, skip DNS updating')

    log_msg("\nWe currently have {} opennodes in reserve".format(currentNodes.__len__()))
    update_time_stamp = str(datetime.now().isoformat(timespec='minutes'))
    log_msg('%s Update finished' % update_time_stamp)
    log_msg('Wait for next update in %d minutes ...' % scanInterval)


if __name__ == '__main__':
    freeze_support()
    while True:
        check_all_nodes()
        time.sleep(scanInterval * 60)
