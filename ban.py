import json
import requests
import dns.resolver

blocklist_domain = 'blocklist.moneropulse.se'


def get_ban_list():
    ban_list = []
    try:
        result = dns.resolver.resolve(blocklist_domain, 'TXT')
        for txt_record in result:
            ban_list = ban_list + str(txt_record).replace('"', '').split(';')
    except dns.exception.DNSException as e:
        print(f"Error querying TXT record for {blocklist_domain}: {e}")
    # print(ban_list)
    return ban_list


def build_filter(ban_list):
    ip_filter = []
    mask24_conuts = {}
    mask16_counts = {}
    for ip in ban_list:
        mask16 = '.'.join(ip.split('.')[:2])
        if mask16 in mask16_counts:
            if mask16_counts[mask16] > 1:
                if mask16 not in ip_filter:
                    ip_filter.append(mask16)
            else:
                mask16_counts[mask16] += 1
        else:
            mask16_counts[mask16] = 0
    for ip in ban_list:
        mask16 = '.'.join(ip.split('.')[:2])
        mask24 = '.'.join(ip.split('.')[:3])
        if mask16 in ip_filter:
            continue
        if mask24 in mask24_conuts:
            if mask24_conuts[mask24] > 1:
                if mask24 not in ip_filter:
                    ip_filter.append(mask24)
            else:
                mask24_conuts[mask24] += 1
        else:
            mask24_conuts[mask24] = 0
    for ip in ban_list:
        mask16 = '.'.join(ip.split('.')[:2])
        mask24 = '.'.join(ip.split('.')[:3])
        if mask16 in ip_filter or mask24 in ip_filter or ip in ip_filter:
            continue
        else:
            ip_filter.append(ip)

    return ip_filter


def ban_node_cluster(node_list_input):
    node_list_output = []
    mask16_counts = {}
    # count cluster
    for ip in node_list_input:
        mask16 = '.'.join(ip.split('.')[:2])
        if mask16 in mask16_counts:
            mask16_counts[mask16] += 1
        else:
            mask16_counts[mask16] = 0
    # pop cluster
    for ip in node_list_input:
        mask16 = '.'.join(ip.split('.')[:2])
        if mask16_counts[mask16] > 2:
            print('Ban %s'%ip)
            continue
        else:
            node_list_output.append(ip)

    return node_list_output

if __name__ == "__main__":
    ban_list = get_ban_list()
    build_filter(ban_list)
