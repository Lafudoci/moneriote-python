# Moneriote-python

moneriote-python is a Python script to maintain DNS records of monero nodes with their RPC port open. It actively scans 
the Monero network through `monerod` and manages DNS records.

An example is the remote node service [node.moneroworld.com](https://moneroworld.com/):

```
dig A node.moneroworld.com

;; ANSWER SECTION:
node.moneroworld.com.	3600	IN	CNAME	opennode.xmr-tw.org.
opennode.xmr-tw.org.	300	IN	A	69.94.198.240
opennode.xmr-tw.org.	300	IN	A	91.121.57.211
opennode.xmr-tw.org.	300	IN	A	139.59.59.176
opennode.xmr-tw.org.	300	IN	A	139.99.195.96
opennode.xmr-tw.org.	300	IN	A	212.83.130.45
```

Supports the following DNS providers: [Cloudflare](https://www.cloudflare.com/), [TransIP](https://transip.nl)


Screenshot
----

![](https://i.imgur.com/VeKZnEX.png)

### Requirements

1. Python >= 3.5
2. Domain name
3. A running and fully synced Monero daemon

Installation
----

```bash
git clone <this repo> python-moneriote
cd python-moneriote
virtualenv -p /usr/bin/python3 venv
source venv/bin/activate
python setup.py develop
```

Moneriote is now installed inside the virtualenv. 


Usage
----

```
Usage: moneriote [OPTIONS]

Options:
  --monerod-path TEXT           Path to the monero daemon executable (monerod).  [default: monerod]
  --monerod-address TEXT        Monero daemon address.  [default: 127.0.0.1]
  --monerod-port INTEGER        Monero daemon port.  [default: 18081]
  --monerod-auth TEXT           Monero daemon auth as 'user:pass'. Will be passed to monerod as `--rpc-login` argument.
  --blockheight-discovery TEXT  Available options: 'monerod', 'xmrchain', 'moneroblocks'. When set to 'compare', it will use all methods and pick the highest
                                blockheight.  [default: compare]
  --dns-provider TEXT           The DNS provider/plugin to use.  [default: cloudflare]
  --domain TEXT                 The domain name without the subdomain. 'example.com'.
  --subdomain TEXT              The subdomain name.  [default: node]
  --api-key TEXT                DNS API key.
  --api-email TEXT              DNS email address or username.
  --max-records INTEGER         Maximum number of DNS records to add.  [default: 5]
  --loop-interval INTEGER       Update loop interval.  [default: 600]
  --scan-interval INTEGER       Interval at which to mass-scan RPC nodes.  [default: 3600]
  --concurrent_scans INTEGER    The amount of servers to scan at once.  [default: 20]
  --ban-list TEXT               Enable ban-list if list path is provided. One IP address per line.
  --from-config TEXT            Load configuration from ini file.
  --help                        Show this message and exit.
```

Example
----

Easiest is to run in `screen` or `tmux`. If you really care about uptime and 
want to babysit the process, write some configuration for `supervisord`  or `systemd`.

```
moneriote --monerod-path "/home/xmr/monero-gui-v0.12.3.0/monerod" 
          --blockheight-discovery "compare" 
          --dns-provider "cloudflare" 
          --domain "example.com" 
          --subdomain "node"
          --api-key "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" 
          --api-email "example@bla.com" 
          --max-records 5
          --ban-list "/home/xmr/block.txt"
```

Flags
----

#### `--monerod-path`

The full path to the monerod executable. On windows this ends on .exe.

##### `--monerod-address`

Default: `127.0.0.1`

The address on which your local monerod is listening

##### `--monerod-port`

Default: `18081`

The port on which your local monerod is listening

##### `--monerod-auth`

The authentication string to use when contacting monerod.

##### `--blockheight-discovery`

Default: `compare`

Available options: `monerod`, `xmrchain`, `moneroblocks`. When set to `compare`, 
it will use all methods and pick the highest blockheight.

`xmrchain` and `moneroblocks` are both Monero explorer websites that expose an API.

##### `--dns-provider`

Available DNS providers: `cloudflare`, `transip`.

If your DNS provider is not included but does provide an API for adding/removing records, 
you can code a custom implementation of `DnsProvider`. See [moneriote/dns/](tree/master/moneriote/dns/)

#### `--domain`

The domain name without the subdomain, example: `example.com`

#### `--subdomain`

The subdomain name, example: `node`

The full domain would become `node.example.com`

#### `--api-key`

The key required by your DNS provider for API access.

#### `--api-email`

The email required by your DNS provider for API access. This flag could also serve for an username, depending 
on `DnsProvider`.

#### `--max-records`

Default: `5`

The maximum amount of records to add.

#### `--loop-interval`

Default: `600`

Shuffle/randomize the records every `X` seconds. Default is 10 minutes.

#### `--scan-interval`

Default: `3600`

Ask monerod for new peers and mass-scan them, every `X` seconds. Default is 1 hour.

#### `--concurrent_scans`

Default: `20`

The amount of servers to scan at once.

#### `--ban-list`

Enable ban-list if list file path is provided. One IP address per line.

#### `--from-config`

Alternatively, configuration can be passed via `config.ini`.

Development
----

Additional DNS provider(s) can be implemented by inheriting from `moneriote.dns.DnsProvider()`. Your custom 
class must implement the following methods. 

#### `def get_records(self)`

Must return a list of nodes (`moneriote.rpc.RpcNodeList`).

#### `def add_record(self, node: RpcNode)`

Adds the A record to the subdomain

#### `def delete_record(self, node: RpcNode):`

Removes the A record from the subdomain.

## History

- Originally developed as a bash script in [Gingeropolous/moneriote](https://github.com/Gingeropolous/moneriote).
- Improved and rewritten in Python by [connorw600/moneriote](https://github.com/connorw600/moneriote/tree/opennodes-python)
- Improved by [Lafudoci/moneriote](https://github.com/Lafudoci/moneriote/tree/opennodes-python)
- Rewritten by [skftn](https://github.com/skftn)
