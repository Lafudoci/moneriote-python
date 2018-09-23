import base64
import os
import time
import uuid
from collections import OrderedDict

import rsa
from suds.client import Client as SudsClient
from suds.sudsobject import Object as SudsObject
from suds.xsd.doctor import Import, ImportDoctor

try:
    from urllib.parse import urlencode, quote_plus
except ImportError:
    from urllib import urlencode, quote_plus

try:
    import suds_requests
except ImportError:
    suds_requests = None

try:
    from Crypto.Hash import SHA512
    from Crypto.Signature import PKCS1_v1_5
    from Crypto.PublicKey import RSA

    HAS_PYCRYPTO = True
except ImportError:
    HAS_PYCRYPTO = False

from moneriote.rpc import RpcNode, RpcNodeList
from moneriote.dns import DnsProvider

URI_TEMPLATE = 'https://{}/wsdl/?service={}'

MODE_RO = 'readonly'
MODE_RW = 'readwrite'


def convert_value(value):
    """
    None and boolean values are not accepted by the Transip API.
    This method converts
        - None and False to an empty string,
        - True to 1
    """
    if isinstance(value, bool):
        return 1 if value else ''

    if not value:
        return ''

    return value


class TransIPDnsEntry(SudsObject):
    def __init__(self, name, expire, record_type, content):
        super(TransIPDnsEntry, self).__init__()
        self.name = name
        self.expire = expire
        self.type = record_type
        self.content = content

    def __eq__(self, other):
        if not hasattr(self, 'name') or not hasattr(self, 'type') or not hasattr(self, 'content'):
            return False
        return self.name == other.name and self.type == other.type and self.content == other.content

    def __repr__(self):
        return '%s %s %s %d' % (self.name, self.type, self.content, self.expire)


class TransIP(DnsProvider):
    """modified https://github.com/benkonrath/transip-api"""
    def __init__(self, **kwargs):
        super(TransIP, self).__init__(**kwargs)
        self.service_name = 'DomainService'
        self.login = kwargs['api_email']
        self.private_key_file = kwargs['api_key']
        self.endpoint = 'api.transip.nl'
        self.url = URI_TEMPLATE.format(self.endpoint, self.service_name)

        imp = Import('http://schemas.xmlsoap.org/soap/encoding/')
        doc = ImportDoctor(imp)

        suds_kwargs = dict()
        if suds_requests:
            suds_kwargs['transport'] = suds_requests.RequestsTransport()

        self.soap_client = SudsClient(self.url, doctor=doc, **suds_kwargs)

    def _sign(self, message):
        """ Uses the decrypted private key to sign the message. """
        if os.path.exists(self.private_key_file):
            with open(self.private_key_file) as private_key:
                keydata = private_key.read()

                if HAS_PYCRYPTO:
                    rsa_key = RSA.importKey(keydata)
                    rsa_ = PKCS1_v1_5.new(rsa_key)
                    sha512_hash_ = SHA512.new()
                    sha512_hash_.update(message.encode('utf-8'))
                    signature = rsa_.sign(sha512_hash_)
                else:
                    privkey = rsa.PrivateKey.load_pkcs1(keydata)
                    signature = rsa.sign(
                        message.encode('utf-8'), privkey, 'SHA-512'
                    )

                signature = base64.b64encode(signature)
                signature = quote_plus(signature)

            return signature
        else:
            raise RuntimeError('The private key does not exist.')

    def _build_signature_message(self, service_name, method_name,
                                 timestamp, nonce, additional=None):
        """
        Builds the message that should be signed. This message contains
        specific information about the request in a specific order.
        """
        if additional is None:
            additional = []

        sign = OrderedDict()
        # Add all additional parameters first
        for index, value in enumerate(additional):
            if isinstance(value, list):
                for entryindex, entryvalue in enumerate(value):
                    if not isinstance(entryvalue, SudsObject):
                        continue

                    for objectkey, objectvalue in entryvalue:
                        objectvalue = convert_value(objectvalue)
                        sign[str(index) + '[' + str(entryindex) + '][' + objectkey + ']'] = objectvalue
            elif isinstance(value, SudsObject):
                for entryindex, entryvalue in value:
                    key = str(index) + '[' + str(entryindex) + ']'
                    sign[key] = convert_value(entryvalue)
            else:
                sign[index] = convert_value(value)
        sign['__method'] = method_name
        sign['__service'] = service_name
        sign['__hostname'] = self.endpoint
        sign['__timestamp'] = timestamp
        sign['__nonce'] = nonce

        return urlencode(sign) \
            .replace('%5B', '[') \
            .replace('%5D', ']') \
            .replace('+', '%20') \
            .replace('%7E', '~')  # Comply with RFC3989. This replacement is also in TransIP's sample PHP library.

    def update_cookie(self, cookies):
        """ Updates the cookie for the upcoming call to the API. """
        temp = []
        for k, val in cookies.items():
            temp.append("%s=%s" % (k, val))

        cookiestring = ';'.join(temp)
        self.soap_client.set_options(headers={'Cookie': cookiestring})

    def build_cookie(self, method, mode, parameters=None):
        """
        Build a cookie for the request.
        Keyword arguments:
        method -- the method to be called on the service.
        mode -- Read-only (MODE_RO) or read-write (MODE_RW)
        """
        timestamp = int(time.time())
        nonce = str(uuid.uuid4())[:32]

        message_to_sign = self._build_signature_message(
            service_name=self.service_name,
            method_name=method,
            timestamp=timestamp,
            nonce=nonce,
            additional=parameters
        )

        signature = self._sign(message_to_sign)

        cookies = {
            "nonce": nonce,
            "timestamp": timestamp,
            "mode": mode,
            "clientVersion": '0.4.1',
            "login": self.login,
            "signature": signature
        }

        return cookies

    def _simple_request(self, method, *args, **kwargs):
        cookie = self.build_cookie(mode=kwargs.get('mode', MODE_RO), method=method, parameters=args)
        self.update_cookie(cookie)
        return getattr(self.soap_client.service, method)(*args)

    def _rpcnode_to_entry(self, node: RpcNode):
        return TransIPDnsEntry(**{
            'name': node.kwargs.get('name', self.subdomain_name),
            'expire': node.kwargs.get('expire', 60),
            'record_type': node.kwargs.get('type', 'A'),
            'content': node.address
        })

    def get_records(self, all_records=False):
        nodes = RpcNodeList()
        cookie = self.build_cookie(mode=MODE_RO, method='getInfo', parameters=[self.domain_name])
        self.update_cookie(cookie)

        result = self.soap_client.service.getInfo(self.domain_name)
        for dnsentry in result.dnsEntries:
            if dnsentry.__class__.__name__ != 'DnsEntry':
                continue
            if dnsentry.type != 'A' and not all_records:
                continue
            if dnsentry.name != self.subdomain_name and not all_records:
                continue
            nodes.append(RpcNode(
                address=dnsentry.content, type=dnsentry.type, name=dnsentry.name, expire=dnsentry.expire))
        return nodes

    def add_record(self, node: RpcNode):
        records = [self._rpcnode_to_entry(_node) for _node in self.get_records(all_records=True)]
        records.append(self._rpcnode_to_entry(node))
        return self._simple_request('setDnsEntries', self.domain_name, records, mode=MODE_RW)

    def delete_record(self, node: RpcNode):
        records = [self._rpcnode_to_entry(_node) for _node in self.get_records(all_records=True) \
                   if _node.address != node.address]
        return self._simple_request('setDnsEntries', self.domain_name, records, mode=MODE_RW)
