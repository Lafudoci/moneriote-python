from datetime import datetime
import random
import json

from dateutil.parser import parse as dateutil_parse

from moneriote import PATH_CACHE, CONFIG
from moneriote.utils import log_msg, log_err, make_json_request


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

    def __add__(self, inp):
        if isinstance(inp, RpcNodeList):
            for node in inp:
                self.append(node)
        elif isinstance(inp, RpcNode):
            self.append(inp)
        return self

    def __len__(self):
        return len(self.nodes)

    def cache_write(self):
        """Writes a cache file of valid nodes"""
        now = datetime.now()
        data = []

        for node in self.nodes:
            if node.valid:
                data.append({'address': node.address,
                             'port': node.port,
                             'dt': now.strftime('%Y-%m-%d %H:%M:%S')})
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
            dt = dateutil_parse(node.pop('dt'))
            if (datetime.now() - dt).total_seconds() < CONFIG['scan_interval'] and 'address' in node:
                nodes.append(RpcNode(**node))

        log_msg('Loaded %d nodes from \'%s\'' % (len(nodes), path))
        return nodes


class RpcNode:
    def __init__(self, address: str, uid=None, port=18089, **kwargs):
        """
        :param address: ip
        :param uid: record uid as per DNS provider
        """
        self.address = address
        self.port = port
        self.uid = uid
        self._acceptableBlockOffset = 3
        self.valid = False
        self.kwargs = kwargs

    @staticmethod
    def is_valid(current_blockheight, obj):
        # Scans the current node to see if the RPC port is available and is within the accepted range
        url = 'http://%s:%d/' % (obj.address, obj.port)
        url = '%s%s' % (url, 'getheight')

        try:
            blob = make_json_request(url, verbose=False, timeout=2)
            if not blob:
                raise Exception()
        except Exception as ex:
            return obj

        if not isinstance(blob.get('height', ''), int):
            return obj

        height = blob.get('height')
        diff = current_blockheight - height

        # Check if the node we're checking is up to date (with a little buffer)
        if diff <= obj._acceptableBlockOffset:
            obj.valid = True
        return obj

    @staticmethod
    def is_updated(current_version, obj):
        # Scans the current node to see if the RPC port is available and is with the accepted version
        url = 'http://%s:%d/' % (obj.address, obj.port)
        url = '%s%s' % (url, 'json_rpc')
        get_version_command = {"jsonrpc":"2.0","id":"0","method":"get_version"}

        try:
            blob = make_json_request(url, method='POST', verbose=False, timeout=2, json=get_version_command)
            if not blob:
                raise Exception()
        except Exception as ex:
            return obj

        if not isinstance(blob.get('result', {}).get('version', ''), int):
            return obj

        version = blob.get('result').get('version')
        diff = current_version - version

        # Check if the node's version we're checking is the same with or newer than ref daemon's version
        if diff >= 0:
            obj.valid = True
        return obj
