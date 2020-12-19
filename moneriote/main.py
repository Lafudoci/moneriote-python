import functools
from time import sleep

import click
click_option = functools.partial(click.option, show_default=True)


@click.command(context_settings=dict(max_content_width=160))
@click_option('--monerod-path', default='monerod', help="Path to the monero daemon executable (monerod).")
@click_option('--monerod-address', default='127.0.0.1', help="Monero daemon address.")
@click_option('--monerod-port', default=18081, help="Monero daemon port.")
@click_option('--monerod-auth', help="Monero daemon auth as 'user:pass'. Will be passed to monerod as "
                                     "`--rpc-login` argument.")
@click_option('--blockheight-discovery', default='compare',
              help="Available options: 'monerod', 'xmrchain', 'moneroblocks'. When set to 'compare', "
                   "it will use all methods and pick the highest blockheight.")
@click_option('--dns-provider', default="cloudflare", help="The DNS provider/plugin to use.")
@click_option('--domain', help="The domain name without the subdomain. 'example.com'.")
@click_option('--subdomain', default="node", help="The subdomain name.")
@click_option('--api-key', help="DNS API key.")
@click_option('--api-email', help="DNS email address or username.")
@click_option('--max-records', default=5, help='Maximum number of DNS records to add.')
@click_option('--loop-interval', default=180, help='Loop interval for quickcheck nodes in cache and DNS records update.')
@click_option('--scan-interval', default=1800, help='Interval at which to mass-scan RPC nodes.')
@click_option('--concurrent_scans', default=20, help='The amount of servers to scan at once.')
@click_option('--ban-list', help='Enable ban-list if list path is provided.')
@click_option('--from-config', help='Load configuration from ini file.')
def cli(monerod_path, monerod_address, monerod_port, monerod_auth, blockheight_discovery,
        dns_provider, domain, subdomain, api_key, api_email, max_records, loop_interval,
        concurrent_scans, scan_interval, ban_list, from_config):
    from moneriote import CONFIG
    from moneriote.moneriote import Moneriote
    from moneriote.utils import log_err, log_msg, banner, parse_ini

    banner()

    if from_config:
        md, dns, ban = parse_ini(from_config)
        monerod_path = md['path']
        monerod_address = md['address']
        monerod_auth = md['auth']
        monerod_port = md['port']
        api_email = dns['api_email']
        api_key = dns['api_key']
        domain = dns['domain_name']
        subdomain = dns['subdomain_name']
        max_records = int(dns['max_records'])
        dns_provider = dns['provider']
        ban_list = ban['ban_list_path']

    if not api_email:
        log_err('Parameter api_email is required', fatal=True)

    if not api_key:
        log_err('Parameter api_key is required', fatal=True)

    if not domain:
        log_err('Parametre domain is required', fatal=True)

    CONFIG['concurrent_scans'] = concurrent_scans
    CONFIG['scan_interval'] = scan_interval

    if dns_provider == 'cloudflare':
        from moneriote.dns.cloudflare import Cloudflare
        dns_provider = Cloudflare(
            domain_name=domain,
            subdomain_name=subdomain,
            api_key=api_key,
            api_email=api_email,
            max_records=max_records)
    elif dns_provider == 'transip':
        from moneriote.dns.transip import TransIP
        dns_provider = TransIP(
            api_email=api_email,
            api_key=api_key,
            subdomain_name=subdomain,
            domain_name=domain,
            max_records=max_records)
    else:
        log_err("Unknown DNS provider \'%s\'" % dns_provider, fatal=True)

    mon = Moneriote(dns_provider=dns_provider,
                    md_path=monerod_path,
                    md_address=monerod_address,
                    md_port=monerod_port,
                    md_auth=monerod_auth,
                    md_height_discovery_method=blockheight_discovery,
                    ban_list_path=ban_list)

    while True:
        mon.main()
        log_msg('Sleeping for %d seconds' % loop_interval)
        sleep(loop_interval)
