#!/usr/bin/env python3
from asyncio.runners import run
import time
import json
import logging
import argparse
import requests
import threading

from flask import Flask

# logging setup
logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')

# application arguments
parser = argparse.ArgumentParser(description='Clustered IP Fencer for Digital Ocean Droplets.')
parser.add_argument('--bind-interface', dest='BIND_INTERFACE', default="0.0.0.0", type=str, help='Network interface to bind to. Default: 0.0.0.0')
parser.add_argument('--bind-port', dest='BIND_PORT', default=4000, type=int, help='Port to bind to. Default: 4000')
parser.add_argument('--advertise-addr', dest='SELF_ADDR', required=True, default=None, type=str, help='Cluster facing addr. Ex: 4.4.4.4:1337')
parser.add_argument('--seeds', dest='SEED_ADDR', required=True, default=None, type=str, help='Comma separated lists of seeds. Ex: 1.1.1.1:1337,2.2.2.2:1337')
parser.add_argument('--loop-rate', dest='LOOP_RATE', default=5, type=int, help='How often the main event loop will run in sections. Default: 5')
args = parser.parse_args()

# setup the member list
SEED_LIST = args.SEED_ADDR.split(',')
MEMBER_LIST = [ args.SELF_ADDR ]
member_list_lock = threading.Lock()

START_TIME = time.time()
LEADER = False
leader_lock = threading.Lock()

MEMBER_STATES = {}
member_states_lock = threading.Lock()

# Just consolidating the entire flask implementation here
def run_flask():
    app = Flask(__name__)
    app.url_map.strict_slashes = False

    # memberlist route
    @app.route('/state') # get memberlist
    @app.route('/state/<addr>') # get memberlist and add new member
    def r_members(addr=None):
        if addr is not None:
            add_member(addr)
        return json.dumps(get_state())

    @app.route('/diag') # for debugging purposes
    def r_diag():
        return json.dumps(cluster_diag(), default=lambda o: '<not serializable>', indent=2) + "\n"

    @app.route('/ping') # quick proof of life
    def r_ping():
        return 'OK'

    # start flask server
    app.run(host=args.BIND_INTERFACE, port=args.BIND_PORT)

# provides complete cluster diagnostic
def cluster_diag():
    return {
            'state': get_state(),
            'member_states': MEMBER_STATES.copy()
        }

# update and get state of this node
def get_state():
    leader_lock.acquire()
    member_list_lock.acquire()
    state = {
            'members': MEMBER_LIST.copy(),
            'leader': LEADER,
            'start_time': START_TIME
        }
    member_list_lock.release()
    leader_lock.release()

    # record this node's state
    member_states_lock.acquire()
    MEMBER_STATES[args.SELF_ADDR] = state.copy()
    member_states_lock.release()
    return state

# the leader should always be the oldest running node... because stability
def election_check():
    global LEADER

    # ensure that other members have been seen before making decisions
    if LEADER == False and len(MEMBER_STATES) <= 1:
        return
    
    # Nominating self
    nominated = args.SELF_ADDR
    time_to_beat = START_TIME

    # look for seniority
    for addr in MEMBER_STATES.keys():
        if MEMBER_STATES[addr]['start_time'] < time_to_beat:
            nominated = addr
            time_to_beat = MEMBER_STATES[addr]['start_time']

    # prevent node from electing itself when there are others that disagree
    if nominated == args.SELF_ADDR and len(MEMBER_LIST) > 1:
        for addr in MEMBER_STATES.keys():
            if addr != args.SELF_ADDR and MEMBER_STATES[addr]['leader'] != nominated:
                logging.info("skipping this election cycle until other members confirm this node can be leader")
                return

    # update the leader 
    if LEADER != nominated:
        logging.info("new leader elected: " + nominated)
        leader_lock.acquire()
        LEADER = nominated
        leader_lock.release()

        # just throw leader_changed into the background
        threading.Thread(target=leader_changed, args=[]).start()

# updates a member's state
def apply_state(addr, state):
    member_states_lock.acquire()
    MEMBER_STATES[addr] = state
    member_states_lock.release()

# removes memeber from memberlist and their state
def remove_member(addr):
    if addr in MEMBER_STATES or addr in MEMBER_LIST:
        logging.info("removing member " + addr)

    if addr in MEMBER_STATES:
        member_states_lock.acquire()
        MEMBER_STATES.pop(addr)
        member_states_lock.release()
        
    if addr in MEMBER_LIST:
        member_list_lock.acquire()
        MEMBER_LIST.remove(addr)
        member_list_lock.release()

# adds a memeber to the memberlist
def add_member(addr):
    # dirty in the list check
    if addr in MEMBER_LIST:
        return

    # test the member
    try:
        res = requests.get('http://' + addr + '/ping', timeout=1)
    except:
        return

    # okay, clean add
    member_list_lock.acquire()
    if addr not in MEMBER_LIST:
        logging.info("adding member via remote state " + addr)
        MEMBER_LIST.append(addr)
    member_list_lock.release()

# gets a copy of a a member's current state
def request_state(addr):
    logging.debug("reading memberlist from " + addr)
    if addr == args.SELF_ADDR:
        return
    
    try:
        res = requests.get('http://' + addr + '/state/' + args.SELF_ADDR, timeout=3)
    except:
        remove_member(addr)
        return

    if res.status_code != 200:
        remove_member(addr)
        return

    state = res.json()

    apply_state(addr, state)

    for addr in state['members']:
        add_member(addr)

# bootstraps memberlist management
def memberlist_loop():
    while True:
        logging.debug("updating memberlist with peers")
        member_list_lock.acquire()
        members = MEMBER_LIST.copy()
        member_list_lock.release()

        threads = []

        # always try seed memberlists
        for seed in SEED_LIST:
            if seed not in members:
                t = threading.Thread(target=request_state, args=[seed])
                t.start()
                threads.append(t)

        # iterate all members to get their memberlists
        for member in members:
            t = threading.Thread(target=request_state, args=[member])
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        election_check()

        time.sleep(args.LOOP_RATE)

# runs in the background every time the leader is changed.
def leader_changed():
    # do a one-off task like so when this node becomes the leader
    if LEADER == args.SELF_ADDR:
        logging.info("WOOT! I AM IN CHARGE NOW!!!!")

    # continuous loop during leadership role
    #while LEADER == args.SELF_ADDR:
    #    time.sleep(1)

# entrypoint
logging.info("IGNORE THE FLASK WARNING ABOUT THIS BEING A DEVELOPMENT SERVER")
threading.Thread(target=memberlist_loop, args=[]).start()
run_flask()