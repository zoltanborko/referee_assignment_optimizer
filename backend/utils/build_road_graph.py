import osmnx as ox
import networkx as nx

# Úthálózat letöltése Hajdú-Bihar vármegyére
G = ox.graph.graph_from_place(
    "Hajdú-Bihar vármegye, Magyarország",
    network_type="drive",
    simplify=True,
    retain_all=True,
)

print(f"Csomópontok száma: {G.number_of_nodes()}")
print(f"Élek száma: {G.number_of_edges()}")

# A gráf mentése későbbi felhasználásra
ox.io.save_graphml(
    G,
    filepath="backend/data/road_network.graphml",
)