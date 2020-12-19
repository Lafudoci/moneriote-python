import json
import requests

ban_list_url = 'https://gui.xmr.pm/files/block.txt'


def get_ban_list():
    ban_list = []
    try:
        resp = requests.get(url=ban_list_url, timeout=30)
        if (resp.status_code != 200):
            return ban_list
    except requests.exceptions.RequestException as err:
        print(err)
        return ban_list

    try:
        for line in resp.text.splitlines():
            ban_list.append(line.strip())

    except Exception as err:
        print('Web content decode error: '+str(err))
        return ban_list

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


if __name__ == "__main__":
    ban_list = get_ban_list()
    build_filter(ban_list)
