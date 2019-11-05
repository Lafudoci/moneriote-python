# Moneriote-python
Python scripts to maintain Monero opennodes DNS records

The moneriote script was originally developed by [Gingeropolous/moneriote](https://github.com/Gingeropolous/moneriote) in command-
line script. The original script was later improved and rewritten in python by [connorw600/moneriote](https://github.com/connorw600/moneriote/tree/opennodes-python) 

This script was modified based on connorw600's work for adopting cloudflare DNS servise API, removed geo-ip and some minor changes.

The moneriote.py use Monero daemon to request peers from another fully synced Monero daemon RPC. All peers IP will be scaned for port-opened 18089 and acceptable block height. Finally 5 usable IP will be updated to cloudflare DNS records.

## Usage
1. Have a fully synced Monero daemon.
2. Edit config.ini for your Monero daemon settiing and cloudflare API information.
3. Run moneriote.py

## Example
The following domain is maintain by this script for 18089 port opennode, DNS records update every 3 minutes.
 * opennode.xmr-tw.org
