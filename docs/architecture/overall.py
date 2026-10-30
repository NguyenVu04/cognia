"""Overall architecture: the processes, the threads, and the one way data moves."""

from diagrams import Cluster, Diagram, Edge
from diagrams.generic.database import SQL
from diagrams.generic.os import Windows
from diagrams.onprem.client import Client, User
from diagrams.onprem.compute import Server
from diagrams.programming.language import Python

graph_attr = {"splines": "spline", "fontsize": "18", "pad": "0.4", "nodesep": "0.7", "ranksep": "1.3"}

with Diagram(
    "Cognia overall architecture",
    filename="images/overall",
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
):
    user = User("the user")
    windows = Windows("Windows")
    data_file = SQL("cognia.sqlite3\nstate tables\nand event log")

    with Cluster("Cognia.exe - one process"):
        with Cluster("GUI thread"):
            surfaces = Python("main window, tray,\ncompanion window")

        with Cluster("sampler thread"):
            sampler = Python("presence sampler\n1 Hz, in memory")

        with Cluster("core thread - the one reader"):
            queue = Python("ordered event queue")
            services = Python("application services")
            rules = Python("pure domain rules\nand SpeechGate")

        with Cluster("model thread"):
            scheduler = Python("model scheduler\none job at a time")

    with Cluster("child processes"):
        chat = Server("llama-server\nchat model")
        embed = Server("llama-server\nembedding model")
        chromium = Client("QtWebEngine\nthree-vrm")

    user >> Edge(label="commands") >> surfaces
    surfaces >> Edge(label="queued signals") >> queue
    windows >> Edge(label="four facts") >> sampler
    sampler >> Edge(label="changes only") >> queue
    queue >> Edge(label="one at a time") >> services
    services >> Edge(label="(state, event)") >> rules
    rules >> Edge(label="(state, effects)", style="dashed") >> services
    services >> Edge(label="one connection") >> data_file
    services >> Edge(label="jobs") >> scheduler
    scheduler >> Edge(label="HTTP on 127.0.0.1") >> [chat, embed]
    scheduler >> Edge(label="results become events", style="dashed") >> queue
    services >> Edge(label="dataclasses", style="dashed") >> surfaces
    surfaces >> Edge(label="expression and motion") >> chromium
