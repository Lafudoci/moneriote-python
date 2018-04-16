from functools import partial
from multiprocessing import Pool, freeze_support
from subprocess import Popen
from time import sleep
from datetime import datetime

import json, re, requests, subprocess, random, configparser

config = configparser.ConfigParser()
config.read('config.ini')

monerodLocation = config.get('MoneroRPC', 'monerodLocation')    # This is the relative or full path to the monerod binary
moneroDaemonAddr = config.get('MoneroRPC', 'moneroDaemonAddr')  # The IP address that the rpc server is listening on
moneroDaemonPort = config.get('MoneroRPC', 'moneroDaemonPort')  # The port address that the rpc server is listening on
moneroDaemonAuth = config.get('MoneroRPC', 'moneroDaemonAuth')  # The username:password that the rpc server requires (if set) - has to be something

doaminName = config.get('cloudflareAPI', 'doaminName')
dnsApiZone = config.get('cloudflareAPI', 'dnsApiZone')
dnsApiKey = config.get('cloudflareAPI', 'dnsApiKey')
dnsApiEmail = config.get('cloudflareAPI', 'dnsApiEmail')
dnsApiUrl = 'https://api.cloudflare.com/client/v4/zones/'+dnsApiZone+'/dns_records/'

headers_cf = {
    'Content-Type': 'application/json',
    'X-Auth-Email': dnsApiEmail,
    'X-Auth-Key': dnsApiKey
}

maximumConcurrentScans = 16   # How many servers we should scan at once
acceptableBlockOffset = 3     # How much variance in the block height will be allowed
scanInterval = 10             # N Minutes
rpcPort = 18089               # This is the rpc server port that we'll check for
currentNodes = []             # store current usable opennodes
dns_record = {}               # store current DNS record


'''
    Gets the current top block on the chain
'''
def get_blockchain_height():
    process = Popen([
        monerodLocation,
        '--rpc-bind-ip', moneroDaemonAddr,
        '--rpc-bind-port', moneroDaemonPort,
        '--rpc-login', moneroDaemonAuth,
        'print_height'],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True, bufsize=1)
    (output, err) = process.communicate()
    height = int(re.sub('[^0-9]', '', output.splitlines()[0]))
    return height

'''
    Gets the last known peers from the server
'''
def load_nodes():

    global currentNodes

    try:
        cn = open( 'current_nodes', 'r')        # read last nodes list from file
        currentNodes = json.loads(cn.read())
        cn.close()
        print('Loaded '+str(currentNodes.__len__())+ ' nodes in current_nodes.')
    except (OSError, IOError) as e:
        print('File current_nodes was not found, will create new.')

    nodes = []
    process = Popen([
        monerodLocation,
        '--rpc-bind-ip', moneroDaemonAddr,
        '--rpc-bind-port', moneroDaemonPort,
        '--rpc-login', moneroDaemonAuth,
        'print_pl'],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True, bufsize=1)
    (output, err) = process.communicate()

    regex = r"(gray|white)\s+(\w+)\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{1,5})"
    matches = re.finditer(regex, output)


    for matchNum, match in enumerate(matches):
        if match.group(1) == 'white':
            address = match.group(3)

            if address not in currentNodes and address != '0.0.0.0':
                nodes.append(address)
    print('Got peers from RPC: ' + str(len(nodes)) + ' nodes')
    return nodes


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
    
    print( 'After screening: ' + str(len(currentNodes)) + ' nodes')

    try:
        cn = open('current_nodes', 'w')
        cn.write(json.dumps(currentNodes))
        cn.close()
    except (OSError, IOError) as e:
        print('Write current_nodes file error:'+e)
    
"""
    Update our dns records
"""
def update_dns_records():
    if currentNodes.__len__() > 5:
        random_record = random.sample(currentNodes, 5)     # random pick 5 records
        print('Random pick 5 IP for DNS records')
    else:
        random_record = currentNodes    # if less than 5 then use all records
        print('Use all IP for DNS records')

    print('Start building records')

    try:
        res_cf = requests.get(url = dnsApiUrl, params = {'name': doaminName, 'per_page': 100}, headers = headers_cf)
        json_cf = json.loads(res_cf.text)
        #print(json_cf)
        if json_cf['success'] == True:
            print('Success When Get DNS List')
            #Create DNS Record
            for node_obj in random_record:
                flag_exist = False
                for list_obj in json_cf['result']:
                    if list_obj['name'] == doaminName and list_obj['content'] == node_obj:
                        flag_exist = True
                        break
                if flag_exist:
                    print(node_obj + ' already exist')
                else:
                    try:
                        res_create = requests.post(url = dnsApiUrl, json = {'name': doaminName, 'type': 'A', 'content': node_obj}, headers = headers_cf)
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
                if list_obj['name'] == doaminName:
                    flag_exist = False
                    for node_obj in random_record:
                        if node_obj == list_obj['content']:
                            flag_exist = True
                            break
                    if not flag_exist:
                        try:
                            res_del = requests.delete(url = dnsApiUrl+list_obj['id'], headers = headers_cf)
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
    # if currentNodes.__len__() > 0:              # scan current existing nodes
    #     print ('Checking existing nodes...')
    #     start_scanning_threads(currentNodes, get_blockchain_height())
    
    print('\nGetting peers...')     # look for new nodes from daemon
    start_scanning_threads(load_nodes(), get_blockchain_height())
    
    print ('Building DNS records...')           # Build DNS records
    if currentNodes.__len__() > 0:
        update_dns_records()
    else:
        print('No availible node, skip DNS updating')
    
    print ("\nWe currently have {} opennodes in reserve".format(currentNodes.__len__()))
    update_time_stamp = str(datetime.now().isoformat(timespec='minutes'))
    print('%s Update finished'% update_time_stamp)
    print('Wait for next update in %d minutes ...'% scanInterval)


if __name__ == '__main__':
    freeze_support()
    while True:
        check_all_nodes()
        sleep(scanInterval * 60)
    