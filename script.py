import json
import random
import requests
import subprocess
import platform
import re
from geopy.distance import geodesic
import matplotlib.pyplot as plt

# Verify that the json file is desired not just a literal list of IPs
IP_FILE = "data\\listed_iperf3_servers.json"
NUM_DESTINATIONS = 5

def ping(ip: str) -> tuple[float, float, float]: # returns (min, max, avg)
    try:
        cmd = []
        if platform.system() == "Windows":
            cmd = ["ping", "-n", "10", ip]
        else:
            cmd = ["ping", "-c", "10", ip]
        res = subprocess.check_output(cmd)
        stats_str_full = res.decode(errors="replace").splitlines()[-1:][0] # string of last line of ping command including "round-trip min/avg/max/stddev =" part
        if platform.system() == "Windows":
            # windows last line is like "Minimum = 226ms, Maximum = 246ms, Average = 238ms"
            stats_arr = re.findall(r"=\s*(\d+(?:\.\d+)?)\s*ms", stats_str_full) # regex to specifically get rid of ms
            if len(stats_arr) != 3:
                raise subprocess.CalledProcessError(1, "ping")
            stats_float_arr = [-1.0, -1.0, -1.0]
            for i in range(len(stats_arr)):
                try:
                    stats_float_arr[i] = float(stats_arr[i])
                except ValueError:
                    raise subprocess.CalledProcessError(1, "ping")
            return (stats_float_arr[0], stats_float_arr[1], stats_float_arr[2])
        else:
            stats_str = stats_str_full.split("=")[1].strip() # string only last part with stats we need
            stats_arr = stats_str.split("/")[:3] # we don't need stdev so get rid of it
            stats_float_arr = [-1.0, -1.0, -1.0]
            for i in range(len(stats_arr)):
                try:
                    stats_float_arr[i] = float(stats_arr[i])
                except ValueError:
                    raise subprocess.CalledProcessError(1, "ping")
            return (stats_float_arr[0], stats_float_arr[2], stats_float_arr[1])
    except subprocess.CalledProcessError:
        print("error pinging")
        return (-1, -1, -1)

def plot_1b(rttanddists):
    #plot avaerage rtt vs distance
    rtts = []
    dists = []

    for loc in rttanddists:
        if (loc[0] > 0 ): #filter out failed geolocating
            rtts.append(loc[0])
            dists.append(loc[1])
     
    plt.scatter(dists, rtts)
    plt.title("Distance vs Round Trip Time")
    plt.xlabel("Distance")
    plt.ylabel("Round Trip Time")
    plt.show()
    return

def load_destinations(path):
    with open(path, "r") as f:
        destinations = json.load(f)
    print(f"Number of entries: {len(destinations)}")
    return destinations


def traceroute(destination):
    # unclear what system this will be run on, I'm on windows so thats the option
    if platform.system() == "Windows":
        command = ["tracert", "-d", destination]
    else:
        command = ["traceroute", "-n", destination]

    result = subprocess.run(command, capture_output=True, text=True, timeout=150) # expressly using 
    # the timout that is the official traceroute failure timeout, bc maybe the process takes a while.
    # i will fight yall on this 
    return parse_traceroute(result.stdout)


def parse_traceroute(output):
    hops = []
    for line in output.splitlines():
        # I *think* this works on both traceroute forms, windows or unix
        match = re.search(
            r"^\s*(\d+)\s+"
            r"(\d+)\s*ms\s+"
            r"(\d+)\s*ms\s+"
            r"(\d+)\s*ms",
            line
        )
        if not match:
            continue
        hop = int(match.group(1))
        rtts = [float(match.group(2)), float(match.group(3)), float(match.group(4))]

        # Average the three traceroute probes
        rtt = sum(rtts) / len(rtts)
        hops.append((hop, rtt))

    return hops

def convert_to_incremental(hops):
    """
        Convert cumulative RTTs into per-hop latency.
        Shoutout chatgpt i didnt think of this
        Example:
            10 ms -> 10 ms
            17 ms ->  7 ms
            25 ms ->  8 ms
    """
      
    result = []
    previous_rtt = 0
    previous_hop = 0

    for hop, rtt in hops:
        # Add missing hops as zero
        for missing_hop in range(previous_hop + 1, hop):
            result.append((missing_hop, 0))

        latency = max(0, rtt - previous_rtt)
        result.append((hop, latency))

        previous_rtt = rtt
        previous_hop = hop

    return result

def plot_results(results):
    destinations = list(results.keys())
    fig, ax = plt.subplots(figsize=(12, 7))

    max_hop = max(
        hop
        for hops in results.values()
        for hop, _ in hops
    )

    bottoms = [0] * len(destinations)
    for hop_num in range(1, max_hop + 1):
        values = []
        for destination in destinations:
            hops = results[destination]
            rtt = next(
                (latency for hop, latency in hops if hop == hop_num),
                0
            )
            values.append(rtt)

        ax.bar(destinations, values, bottom=bottoms, label=f"Hop {hop_num}")
        bottoms = [
            bottom + value
            for bottom, value in zip(bottoms, values)
        ]

    ax.set_xlabel("Destination")
    ax.set_ylabel("Latency (ms)")
    ax.set_title("Traceroute Latency by Destination")

    ax.legend(title="Hop")
    plt.xticks(rotation=30)
    plt.tight_layout()
    plt.show()

def plot_2c(results):
    fig, ax = plt.subplots(figsize=(12, 7))
    #plotting hopcount against time
    #I need to add up the hop time
    #which we had before zach so graciously converted it to incremental
    hopcounts = []
    rtts = []

    destinations = list(results.keys())
    for dest in destinations:
        hops = results[dest]
        #^ list of hops
        rtt = 0
        hopct = 0
        for hop in hops:
            rtt += hop[1]
            if (hop[1] != 0): #filter out nonresponsive hops
                hopct += 1
        hopcounts.append(hopct)
        rtts.append(rtt)
        #print(dest)
        #print("Rtt:", rtt)
        #print("hops:", hopct)

    plt.scatter(rtts, hopcounts)
    plt.title("Round Trip Time vs Hop Count")
    plt.xlabel("Round Trip Time")
    plt.ylabel("Hop Count")
    plt.show()

    return

def main():
    my_ip = requests.get("https://api.ipify.org?format=json").json()["ip"]

    my_geo = requests.get("http://ip-api.com/json/" + my_ip).json()

    print("[*] My ip:", my_ip)
    print("[*] My geo:", my_geo)
    my_min, my_max, my_avg = ping(my_ip)
    print(f"[*] My ping min/max/avg: {my_min}/{my_max}/{my_avg}")

    servers = requests.get("http://export.iperf3serverlist.net/listed_iperf3_servers.json").json() # i'm gonna be so real i didn't realize we were supposed to use a downloaded file to pull the data so I just used their json file instead

    server_infos = []
    rttanddists = [] #I refuse to use subdictionaries

    for server in servers:
        print(f"[*] Pinging server at {server['IP/HOST']}")
        ping_res = ping(server['IP/HOST'])
        geo_res = requests.get("http://ip-api.com/json/" + server['IP/HOST']).json()
        try:
            server_infos.append({
                    "server": server['IP/HOST'],
                    "ping_stats": ping_res,
                    "geo_stats": geo_res,
                    "distance": geodesic((my_geo["lat"], my_geo["lon"]), (geo_res["lat"], geo_res["lon"])).miles
                }
            )
            dist = geodesic((my_geo["lat"], my_geo["lon"]), (geo_res["lat"], geo_res["lon"])).miles
            if (dist != 0) :
                rttanddists.append([ping_res[2], dist])
        except KeyError: # in the case that an ip does not have geolocation
            server_infos.append({
                    "server": server['IP/HOST'],
                    "ping_stats": ping_res,
                    "geo_stats": geo_res,
                    "distance": -1
                }
            )

    for server_info in server_infos:
        outstr = f"[*] Server {server_info['server']} "
        if server_info["ping_stats"] == (-1, -1, -1):
            outstr += "did not respond to ping and "
        else:
            min, max, avg = server_info['ping_stats']
            outstr += f"min/max/avg ping = {min}/{max}/{avg} and "
        if server_info["distance"] == -1:
            outstr += "did not have geolocation details."
        else:
            outstr += f"is located at lat/lon = {server_info['geo_stats']['lat']}/{server_info['geo_stats']['lon']}."
        print(outstr)
    plot_1b(rttanddists)

    destinations = load_destinations(IP_FILE)

    # robustness
    if len(destinations) < NUM_DESTINATIONS:
        raise ValueError(
            f"Need at least {NUM_DESTINATIONS} destinations"
        )

    remaining = destinations.copy()
    results = {}

    print("\nSelected destinations:")

    while len(results) < NUM_DESTINATIONS and remaining:
        entry = random.choice(remaining)
        remaining.remove(entry)
        destination = entry["IP/HOST"]

        print(f"  {destination}, {entry['COUNTRY']}")
        # try except loop for robustness / preventing issues if networking is finicky
        try:
            hops = traceroute(destination)
            print(f" Destination {destination} RTTs")

            if not hops:
                print("No Response, selecting another")
                continue

            hops = convert_to_incremental(hops)

            results[destination] = hops
        except subprocess.TimeoutExpired:
            print("Traceroute timed out; selecting another")

        except Exception as e:
            print(f"Error: {e}; selecting another")

    if len(results) < NUM_DESTINATIONS:
        raise RuntimeError(
            f"Could only obtain {len(results)} successful "
            f"traceroutes from {len(destinations)} destinations"
        )
    print(results)
    
    plot_results(results)
    plot_2c(results)


if __name__ == "__main__":
    main()