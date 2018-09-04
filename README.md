# Moneriote-python
Python scripts to maintain Monero opennodes DNS records via Cloudflare.


#### History
- Originally developed by [Gingeropolous/moneriote](https://github.com/Gingeropolous/moneriote) as a bash script.
- Improved and rewritten in Python by [connorw600/moneriote](https://github.com/connorw600/moneriote/tree/opennodes-python)
- Improved by [Lafudoci/moneriote](https://github.com/Lafudoci/moneriote/tree/opennodes-python)
- Refactored/rewritten by [skftn/dsc](https://github.com/skftn)

#### Usage

You have:
1. A Cloudflare account with an API key
2. A fully synced Monero daemon
3. A correct `config.ini`
4. A Python >= 3.5 interpreter with `requests` installed (`pip install requests`).

The program loop looks like this:

1. Ask `monerod` for the blockchain height, or consult `xmrchain.net`. Or both, as specified by `config.ini`.
2. Fetch the correct `zone_id` from Cloudflare
3. Ask Cloudflare for existing A records, for example all the IPs belonging to `node.example.com`.
4. Verify those records, by scanning the nodes for `http://<ip>:18089/get_height`
    - Remove nodes who do not respond in time
    - Remove nodes who seem to lag behind in blockchain height
5. Ask `monerod` for a peer list (`print_pl`), it will result in ~1000 incoming nodes/peers.
6. Mass scan the list of peers on port `18089`, try to fetch `/get_height`. Confirm acceptable blockheight.
7. Insert a Cloudflare `A` record for valid nodes, but not more than `max_records`.
8. Repeat.

To summarize, this script actively searches the Monero network for nodes that have their RPC exposed to
the world. It automatically removes the records who do not seem to be valid anymore.

## Example
The following domain is maintained by this script. It updates every 10 minutes:
 * opennode.xmr-tw.org

Example usage:

```
$ python moneriote.py

[2018-09-05 00:19] xmrchain height is 1654185
[2018-09-05 00:19] using xmrchain height
[2018-09-05 00:19] Determining zone_id; looking for 'xmr-tw.org'
[2018-09-05 00:19] Contacting Cloudflare (GET): https://api.cloudflare.com/client/v4/zones/
[2018-09-05 00:19] Cloudflare zone_id 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' matched to 'xmr-tw.org'
[2018-09-05 00:19] Fetching existing record(s) (opennode.xmr-tw.org)
[2018-09-05 00:19] Contacting Cloudflare (GET): https://api.cloudflare.com/client/v4/zones/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/dns_records/
[2018-09-05 00:19] Found 0 existing record(s) on Cloudflare
[2018-09-05 00:19] Trying to find 5 more nodes to add to Cloudflare
[2018-09-05 00:19] spawning daemon; executing command 'print_pl'
[2018-09-05 00:19] Got peers from RPC: 990 node(s)
[2018-09-05 00:19] Scanning 990 node(s) on port 18089. This can take several minutes. Let it run.
[2018-09-05 00:19] Scanning 990 node(s) done after 8 seconds, found 2 valid
[2018-09-05 00:19] Cloudflare record insertion: 73.115.113.104
[2018-09-05 00:19] Contacting Cloudflare (POST): https://api.cloudflare.com/client/v4/zones/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/dns_records
[2018-09-05 00:19] Cloudflare record insertion: 108.61.251.120
[2018-09-05 00:19] Contacting Cloudflare (POST): https://api.cloudflare.com/client/v4/zones/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/dns_records
[...]
```