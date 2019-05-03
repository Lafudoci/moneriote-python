import time
from moneriote.dns import DnsProvider
from moneriote.rpc import RpcNode, RpcNodeList
from moneriote.utils import log_err, log_msg, random_user_agent, make_json_request


class Cloudflare(DnsProvider):
    def __init__(self, **kwargs):
        super(Cloudflare, self).__init__(**kwargs)

        self.headers = {
            'Content-Type': 'application/json',
            'X-Auth-Email': kwargs['api_email'],
            'X-Auth-Key': kwargs['api_key'],
            'User-Agent': random_user_agent()
        }
        self.api_base = 'https://api.cloudflare.com/client/v4/zones'
        self.zone_id = None

        # zone_id is required and will be detected via Cloudflare API
        if not self.zone_id:
            log_msg('Determining zone_id; looking for \'%s\'' % self.domain_name)
            result = make_json_request(url=self.api_base, headers=self.headers)
            try:
                zones = result.get('result')
                self.zone_id = next(zone.get('id') for zone in zones if zone.get('name') == self.domain_name)
            except StopIteration:
                log_err('could not determine zone_id. Is your Cloudflare domain correct?', fatal=True)
            log_msg('Cloudflare zone_id \'%s\' matched to \'%s\'' % (self.zone_id, self.domain_name))

    def get_records(self):
        max_retries = 5
        nodes = RpcNodeList()
        log_msg('Fetching existing record(s) (%s.%s)' % (self.subdomain_name, self.domain_name))

        retries = 0
        while (True):
            try:
                result = make_json_request('%s/%s/dns_records/?type=A&name=%s.%s' % (
                    self.api_base, self.zone_id,
                    self.subdomain_name, self.domain_name), headers=self.headers)
                records = result.get('result')
                
                # filter on A records / subdomain
                for record in records:
                    if record.get('type') != 'A' or record.get('name') != self.fulldomain_name:
                        continue

                    node = RpcNode(address=record.get('content'), uid=record.get('id'))
                    nodes.append(node)
                    log_msg('> A %s %s' % (record.get('name'), record.get('content')))
                return nodes
            
            except Exception as ex:
                log_err("Cloudflare record fetching failed: %s" % (str(ex)))
                retries += 1
                time.sleep(1)
                if retries > max_retries:
                    return None
        

    def add_record(self, node: RpcNode):
        log_msg('Record insertion: %s' % node.address)

        try:
            url = '%s/%s/dns_records' % (self.api_base, self.zone_id)
            make_json_request(url=url, method='POST', verbose = False, headers=self.headers, json={
                'name': self.subdomain_name,
                'content': node.address,
                'type': 'A',
                'ttl': 120
            })
        except Exception as ex:
            log_err("Cloudflare record (%s) insertion failed: %s" % (node.address, str(ex)))

    def delete_record(self, node: RpcNode):
        # Delete DNS Record
        log_msg('Cloudflare record deletion: %s' % node.address)

        try:
            url = '%s/%s/dns_records/%s' % (self.api_base, self.zone_id, node.uid)
            data = make_json_request(url=url, method='DELETE', verbose = False, headers=self.headers)
            assert data.get('success') is True
            return data.get('result')
        except Exception as ex:
            log_err("Record (%s) deletion failed: %s" % (node.address, str(ex)))
