import time
import osmnx as ox
import networkx as nx

ox.settings.requests_timeout = 180
ox.settings.use_cache = True

# Úthálózat letöltése Hajdú-Bihar vármegyére
G = ox.graph.graph_from_place(
    "Hajdú-Bihar vármegye, Magyarország",
    network_type="drive",
    simplify=True,
    retain_all=True,
)

extra_places = [
    "Érmihályfalva, Bihor, Romania",
    "Szorgalmatos, Szabolcs-Szatmár-Bereg, Hungary",
]

for place in extra_places:
    print(f"Úthálózat letöltése: {place}")

    lat, lon = ox.geocoder.geocode(place)

    for attempt in range(3):
        try:
            G_extra = ox.graph.graph_from_point(
                (lat, lon),
                dist=15000,
                network_type="drive",
            )

            G = nx.compose(G, G_extra)
            print(f"Sikeres: {place}")
            break

        except ox._errors.ResponseStatusCodeError as e:
            if attempt == 2:
                raise

            wait = 30 * (attempt + 1)
            print(f"Overpass-hiba: {e}")
            print(f"Újrapróbálkozás {wait} másodperc múlva...")
            time.sleep(wait)

print(f"Csomópontok száma: {G.number_of_nodes()}")
print(f"Élek száma: {G.number_of_edges()}")

# A gráf mentése későbbi felhasználásra
ox.io.save_graphml(
    G,
    filepath="backend/data/road_network.graphml",
)