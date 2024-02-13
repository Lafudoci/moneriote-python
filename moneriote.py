from functools import partial
from multiprocessing import Pool, freeze_support
from subprocess import Popen
from datetime import datetime

import json, re, requests, subprocess, random, configparser, time

import ban
import sys

config = configparser.ConfigParser()
config.read('config.ini')

moneroDaemonAddr = config.get('MoneroRPC', 'moneroDaemonAddr')  # The IP address that the rpc server is listening on
moneroDaemonPort = config.get('MoneroRPC', 'moneroDaemonPort')  # The port address that the rpc server is listening on
moneroDaemonAuth = config.get('MoneroRPC', 'moneroDaemonAuth')  # The username:password that the rpc server requires (if set) - has to be something

domainName = config.get('cloudflareAPI', 'domainName')
allDomainName = config.get('cloudflareAPI', 'allDomainName')
dnsApiZone = config.get('cloudflareAPI', 'dnsApiZone')
dnsApiKey = config.get('cloudflareAPI', 'dnsApiKey')
dnsApiEmail = config.get('cloudflareAPI', 'dnsApiEmail')
dnsApiUrl = 'https://api.cloudflare.com/client/v4/zones/'+dnsApiZone+'/dns_records/'

banListUrl = config.get('banList', 'banListUrl')

headers_cf = {
    'Content-Type': 'application/json',
    'X-Auth-Email': dnsApiEmail,
    'X-Auth-Key': dnsApiKey
}

maximumConcurrentScans = 16   # How many servers we should scan at once
acceptableBlockOffset = 3     # How much variance in the block height will be allowed
# scanInterval = 60             # N Minutes for mass scan RPC peers
shuffleInterval = 3            # N Minutes for quick shuffle current DNS records
recordNum = 5                 # Max number of DNS record to keep
rpcPort = 18089               # This is the rpc server port that we'll check for
currentNodes = []             # store current usable opennodes
dns_record = {}               # store current DNS record
ban_list = []                 # Store IP filter


'''
    Gets the current top block on the chain
'''
def get_blockchain_height():
    daemon_height = 0
    retry = 0
    while True:
        try:
            # Gets height from daemon
            url = "http://%s:%s/get_height"%(moneroDaemonAddr, moneroDaemonPort)
            headers = {"Content-Type": "application/json"}
            response = requests.get(url, headers=headers, timeout=20)
            if response.status_code == 200:
                data = response.json()
                status = data.get('status')
                if status == 'OK':
                    daemon_height = int(data.get('height'))
                    print('Daemon height is '+ str(daemon_height))
                    return daemon_height
                else:
                    print(' ERROR: Daemon not respond OK')
                    print(' Retry in 10s ...')
                    retry += 1
                    time.sleep(10)
            else:
                print(' ERROR: HTTP code %d'%response.status_code)
                print(' Retry in 10s ...')
                time.sleep(10)
                retry += 1
        except requests.exceptions.RequestException as err:
            print(' ERROR: '+ str(err))
            print(' Retry in 10s ...')
            time.sleep(10)
            retry += 1
        if retry > 10:
            print(' ERROR: Could not get height from Daemon, max retry, exiting')
            sys.exit()



'''
    Gets the last known peers from the server
'''
def load_peers():
    nodes = []
    url = "http://%s:%s/get_peer_list"%(moneroDaemonAddr, moneroDaemonPort)
    headers = {"Content-Type": "application/json"}
    response = requests.get(url, headers=headers, timeout=20)
    if response.status_code == 200:
        data = response.json()
        status = data.get('status')
        if status == 'OK':
            for peer in data["white_list"]:
                address = f"{peer['ip'] // 2**24}.{peer['ip'] // 2**16 % 256}.{peer['ip'] // 2**8 % 256}.{peer['ip'] % 256}"
                if address not in currentNodes and address != '0.0.0.0':
                    nodes.append(address)
            print('Got peers from RPC: ' + str(len(nodes)) + ' nodes')
        else:
            print(f"Status Error: {status}")
    else:
        print(f"HTTP Error: {response.status_code}")
    return nodes


"""
    Load local current nodes cache from file
"""
def load_cache():
    current_nodes = []
    try:
        cn = open( 'current_nodes', 'r')
        current_nodes = json.loads(cn.read())
        cn.close()
        print('Loaded '+str(current_nodes.__len__())+ ' nodes in current_nodes.')
    except (OSError, IOError) as e:
        print('File current_nodes was not found, will create new.')
    return current_nodes


"""
    Scans the requested address to see if the RPC port is available and is within the accepted range
"""
def scan_node(accepted_height, address):

    try:
        req = requests.get('http://' + address + ':' + rpcPort.__str__() + '/getheight', timeout=3)
    except requests.exceptions.RequestException:
        return {'address': address, 'valid': False}

    try:
        node_height_json = json.loads(req.text)
    except:
        return {'address': address, 'valid': False}

    block_height_diff = int(node_height_json['height']) - accepted_height

    # Check if the node we're checking is up to date (with a little buffer)
    if acceptableBlockOffset >= block_height_diff >= (acceptableBlockOffset * -1):
        return {'address': address, 'valid': True}
    else:
        return {'address': address, 'valid': False}



"""
    Start threads checking known nodes to see if they're alive
"""
def start_scanning_threads(current_nodes, blockchain_height):

    global currentNodes

    current_nodes = node_filter(current_nodes)

    print('Scanning port '+ str(rpcPort) +' online & synced (height '+str(blockchain_height)+') nodes...')

    pool = Pool(processes=maximumConcurrentScans)
    response = pool.map(partial(scan_node, blockchain_height), current_nodes)

    pool.close()
    pool.join()

    for node in response:
        if node['valid'] is True and node['address'] not in currentNodes:
            currentNodes.append(node['address'])

        if node['valid'] is False and node['address'] in currentNodes:
            currentNodes.remove(node['address'])
    
    print('Banning cluster nodes.')
    currentNodes = ban.ban_node_cluster(currentNodes)

    print( 'After screening: ' + str(len(currentNodes)) + ' nodes')

    try:
        cn = open('current_nodes', 'w')
        cn.write(json.dumps(currentNodes))
        cn.close()
    except (OSError, IOError) as e:
        print('Write current_nodes file error:'+e)
    
"""
    Random pick records from all valid nodes
"""
def random_pick_nodes():
    if currentNodes.__len__() > recordNum:
        random_record = random.sample(currentNodes, recordNum)     # random pick records
        print('Random pick %d IP for DNS records'%recordNum)
    else:
        random_record = currentNodes.copy()    # if less than recordNum then use all records
        print('Use all IP for DNS records')

    return random_record

"""
    Update our dns records
"""
def update_dns_records(domain, records):

    print('Start building records of ' + str(domain))

    try:
        res_cf = requests.get(url = dnsApiUrl, params = {'name': domain, 'per_page': 500}, headers = headers_cf, timeout = 30)
        json_cf = json.loads(res_cf.text)
        #print(json_cf)
        if json_cf['success'] == True:
            print('Success When Get DNS List')
            #Create DNS Record
            for node_obj in records:
                flag_exist = False
                for list_obj in json_cf['result']:
                    if list_obj['name'] == domain and list_obj['content'] == node_obj:
                        flag_exist = True
                        break
                if flag_exist:
                    print(node_obj + ' already exist')
                else:
                    try:
                        res_create = requests.post(url = dnsApiUrl, json = {'name': domain, 'type': 'A', 'content': node_obj}, headers = headers_cf, timeout = 30)
                        json_create = json.loads(res_create.text)
                        if json_create['success'] == True:
                            print(node_obj + ' create record success')
                        else:
                            print(node_obj + ' create record fail')
                            print(res_create.text)
                    except (requests.exceptions.RequestException, ValueError) as err:
                        print(str(err))
            #Delete DNS Record
            for list_obj in json_cf['result']:
                if list_obj['name'] == domain:
                    flag_exist = False
                    for node_obj in records:
                        if node_obj == list_obj['content']:
                            flag_exist = True
                            break
                    if not flag_exist:
                        try:
                            res_del = requests.delete(url = dnsApiUrl+list_obj['id'], headers = headers_cf, timeout = 30)
                            json_del = json.loads(res_del.text)
                            if json_del['success'] == True:
                                print(list_obj['content'] + ' delete record success')
                            else:
                                print(list_obj['content'] + ' delete record fail')
                                print(res_del.text)
                        except (requests.exceptions.RequestException, ValueError) as err:
                            print(str(err))
        else:           
            print('Error When Get DNS List')
    except (requests.exceptions.RequestException, ValueError) as err:
        print(str(err))


def check_all_nodes():

    global currentNodes

    currentNodes = load_cache()

    if currentNodes.__len__() > 0:              # scan current existing nodes
        print ('Checking existing nodes...')
        start_scanning_threads(currentNodes, get_blockchain_height())
    
    print('\nGetting new peers...')     # look for new nodes from daemon
    start_scanning_threads(load_peers(), get_blockchain_height())
    
    print ('Building DNS records...')           # Build DNS records
    if currentNodes.__len__() > 0:
        update_dns_records(domainName, random_pick_nodes())
        if allDomainName != '':
            update_dns_records(allDomainName, currentNodes)
    else:
        print('No availible node, skip DNS updating')
    
    print ("\nWe currently have {} opennodes in reserve".format(currentNodes.__len__()))
    update_time_stamp = str(datetime.now().isoformat(timespec='minutes'))
    print('%s Update finished'% update_time_stamp)
    print('Wait for next update in %d minutes ...'% shuffleInterval)


"""
Quick shuffle of DNS records
"""
def shuffle_nodes():
    print ('Shuffling DNS records...')
    
    global currentNodes
    
    currentNodes = load_cache()

    if currentNodes.__len__() > 0:
        print ('Checking existing nodes...')
        start_scanning_threads(currentNodes, get_blockchain_height())
        if currentNodes.__len__() > recordNum:
            print ('Building DNS records...')
            update_dns_records(domainName, random_pick_nodes())
            print ("\nWe currently have {} opennodes in reserve".format(currentNodes.__len__()))
            update_time_stamp = str(datetime.now().isoformat(timespec='minutes'))
            print('%s Shuffle finished'% update_time_stamp)
            print('Wait for next update in %d minutes ...'% shuffleInterval)
        else:
            print('No availible node, skip DNS updating')
            return -1
    else:
        print('No availible node, skip DNS updating')
        return -1


"""
Build node filter from ban-list
"""
def node_filter(node_list_input):
    global ban_filter
    ban_list = ban.get_ban_list()
    print('Got %d nodes from ban-list'%len(ban_list))
    if len(ban_list) > 0:
        ban_filter = ban.build_filter(ban_list)
    for ip in node_list_input:
        mask16 = '.'.join(ip.split('.')[:2])
        mask24 = '.'.join(ip.split('.')[:3])
        if mask16 in ban_filter or mask24 in ban_filter or ip in ban_filter:
            node_list_input.remove(ip)
            print('Ban %s'%ip)
    return node_list_input

if __name__ == '__main__':
    freeze_support()
    while True:
        check_all_nodes()
        i = 0
        while i < 20:
            time.sleep(shuffleInterval * 60)
            if shuffle_nodes() == -1:
                break
            i += 1
            
