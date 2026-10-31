"""System context: Cognia as one box, and everything outside it."""

from diagrams import Cluster, Diagram, Edge
from diagrams.generic.database import SQL
from diagrams.generic.os import Windows
from diagrams.onprem.client import User
from diagrams.onprem.compute import Server

graph_attr = {"splines": "spline", "fontsize": "18", "pad": "0.4", "nodesep": "0.8", "ranksep": "1.5"}

with Diagram(
    "Cognia system context",
    filename="images/context",
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
):
    user = User("the user\n(one person)")

    with Cluster("one Windows machine"):
        with Cluster("Cognia"):
            system = Server("Cognia\napplication and\nshipped AI models")

        windows = Windows("Windows\nfour facts and\nscreen layout")
        disk = SQL("the user's disk\none SQLite file")

    user >> Edge(label="talks, sets limits, reads memory") >> system
    system >> Edge(label="speaks, shows feelings, explains") >> user
    windows >> Edge(label="idle, lock, presenting,\nforeground application name") >> system
    system >> Edge(label="reads and writes") >> disk
