import json
import os
import osmnx as ox
import networkx as nx

# Korábban letöltött közúthálózat
G = ox.io.load_graphml(
    "backend/data/road_network.graphml"
)

settlements = [
    "Álmosd",
    "Ártánd",
    "Bagamér",
    "Bakonszeg",
    "Balmazújváros",
    "Báránd",
    "Bedő",
    "Berekböszörmény",
    "Berettyóújfalu",
    "Bihardancsháza",
    "Biharkeresztes",
    "Biharnagybajom",
    "Bihartorda",
    "Bocskaikert",
    "Bojt",
    "Csökmő",
    "Darvas",
    "Debrecen",
    "Derecske",
    "Ebes",
    "Egyek",
    "Esztár",
    "Érmihályfalva",
    "Földes",
    "Folyás",
    "Fülöp",
    "Furta",
    "Gáborján",
    "Görbeháza",
    "Hajdúbagos",
    "Hajdúböszörmény",
    "Hajdúdorog",
    "Hajdúhadház",
    "Hajdúnánás",
    "Hajdúsámson",
    "Hajdúszoboszló",
    "Hajdúszovát",
    "Hencida",
    "Hortobágy",
    "Hosszúpályi",
    "Kaba",
    "Kismarja",
    "Kokad",
    "Komádi",
    "Konyár",
    "Körösszakál",
    "Körösszegapáti",
    "Létavértes",
    "Magyarhomorog",
    "Mezőpeterd",
    "Mezősas",
    "Mikepércs",
    "Monostorpályi",
    "Nádudvar",
    "Nagyhegyes",
    "Nagykereki",
    "Nagyrábé",
    "Nyírábrány",
    "Nyíracsád",
    "Nyíradony",
    "Nyírmártonfalva",
    "Pocsaj",
    "Polgár",
    "Püspökladány",
    "Sáp",
    "Sáránd",
    "Sárrétudvari",
    "Szentpéterszeg",
    "Szerep",
    "Szorgalmatos",
    "Téglás",
    "Tépe",
    "Tetétlen",
    "Tiszacsege",
    "Tiszagyulaháza",
    "Told",
    "Újiráz",
    "Újléta",
    "Újszentmargita",
    "Újtikos",
    "Vámospércs",
    "Váncsod",
    "Vekerd",
    "Zsáka"
]

# Települések koordinátái és legközelebbi úthálózati csomópontjai
settlement_nodes = {}

for settlement in settlements:
    if settlement == "Érmihályfalva":
        query = "Érmihályfalva, Bihor, Romania"
    elif settlement == "Szorgalmatos":
        query = "Szorgalmatos, Hungary"
    else:
        query = f"{settlement}, Hajdú-Bihar, Hungary"

    lat, lon = ox.geocoder.geocode(query)
    lat, lon = ox.geocoder.geocode(query)

    node = ox.distance.nearest_nodes(
        G,
        X=lon,
        Y=lat,
    )

    settlement_nodes[settlement] = node

# Településpárok legrövidebb közúti távolságai
distances = {}

for source, source_node in settlement_nodes.items():
    distances[source] = {}

    lengths = nx.single_source_dijkstra_path_length(
        G,
        source=source_node,
        weight="length",
    )

    for target, target_node in settlement_nodes.items():
        if target_node in lengths:
            # Méter helyett kilométer
            distances[source][target] = round(
                lengths[target_node] / 1000,
                2,
            )
        else:
            distances[source][target] = None

os.makedirs("backend/data", exist_ok=True)

with open(
    "backend/data/distances.json",
    "w",
    encoding="utf-8",
) as file:
    json.dump(
        distances,
        file,
        ensure_ascii=False,
        indent=2,
    )

print("Távolságok elmentve!")