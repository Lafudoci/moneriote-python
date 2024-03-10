import requests
import socket
import json


def url_to_ip(url):

    if "://" in url:
        url = url.split("://")[1]
    if ":" in url:
        url = url.split(":")[0]

    try:
        return socket.gethostbyname(url)
    except socket.gaierror:
        return None


def main():

    response = requests.get("https://monero.fail/nodes.json")
    url_list = response.json()["monero"]["clear"]
    ip_list = set()
    for url in url_list:
        if url.endswith("18089"):
            ip = url_to_ip(url)
            if ip != None:
                ip_list.add(ip)

    for ip_address in ip_list:
        print(ip_address)

    with open("seed_nodes", "w") as f:
        f.write(json.dumps(list(ip_list)))


if __name__ == "__main__":
    main()
