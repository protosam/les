# Leader Election by Seniority (LES)
This algorithm came from a necessity to bounce an IP address between Cloud Server nodes. It can be used to implement and manage pretty much any resources though.

# Python Implementation
A Python template for clustered leadership elections, where the most senior node wins.

Copy `les-example.py` and implement `leader_changed()`.

## The Algorithm Rules
* Nodes share their memberlist upon request
* Nodes will attempt to add new members when informed of the new node
* Nodes will always retry seed nodes and add active seeds to the memberlist
* Nodes will remove members it can't contact
* Nodes can not do election until it has communicated with other nodes
* Nodes will always accept the most senior node as the leader
* If a node elects itself, it must wait for other members to confirm first, unless it's alone

## Demo
You can just run 3 nodes locally with the following commands in separate terminals.
```text
$ python3 les-example.py --bind-port 4000 --advertise-addr localhost:4000 --seeds localhost:4000,localhost:4001,localhost:4002
$ python3 les-example.py --bind-port 4001 --advertise-addr localhost:4001 --seeds localhost:4000,localhost:4001,localhost:4002
$ python3 les-example.py --bind-port 4002 --advertise-addr localhost:4002 --seeds localhost:4000,localhost:4001,localhost:4002
```

You can view the entire state via curl from any node:
```text
$ curl -s localhost:4002/diag/
{
  "state": {
    "members": [
      "localhost:4002",
      "localhost:4000",
      "localhost:4001"
    ],
    "leader": "localhost:4000",
    "start_time": 1627515915.703066
  },
  "member_states": {
    "localhost:4000": {
      "members": [
        "localhost:4000",
        "localhost:4001",
        "localhost:4002"
      ],
      "leader": "localhost:4000",
      "start_time": 1627515912.646504
    },
    "localhost:4001": {
      "members": [
        "localhost:4001",
        "localhost:4000",
        "localhost:4002"
      ],
      "leader": "localhost:4000",
      "start_time": 1627515914.368885
    },
    "localhost:4002": {
      "members": [
        "localhost:4002",
        "localhost:4000",
        "localhost:4001"
      ],
      "leader": "localhost:4000",
      "start_time": 1627515915.703066
    }
  }
}
```