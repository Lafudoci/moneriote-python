from moneriote.rpc import RpcNode


class DnsProvider(object):
    def __init__(self, **kwargs):
        self.domain_name = kwargs['domain_name']
        self.subdomain_name = kwargs['subdomain_name']
        self.api_key = kwargs['api_key']
        self.api_email = kwargs['api_email']
        self.max_records = kwargs['max_records']
        self.headers = {}

    @property
    def fulldomain_name(self):
        return '%s.%s' % (self.subdomain_name, self.domain_name)

    def get_records(self):
        raise NotImplementedError()

    def add_record(self, node: RpcNode):
        raise NotImplementedError()

    def delete_record(self, node: RpcNode):
        raise NotImplementedError()


from moneriote.dns.cloudflare import Cloudflare