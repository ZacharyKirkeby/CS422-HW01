import requests
import subprocess
import platform
import re
from geopy.distance import geodesic
import matplotlib.pyplot as plt

def ping(ip: str) -> tuple[float, float, float]: # returns (min, max, avg)
    try:
        cmd = []
        if platform.system() == "Windows":
            cmd = ["ping", "-n", "4", ip]
        else:
            cmd = ["ping", "-c", "4", ip]
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
                server['IP/HOST']: {
                    "ping_stats": ping_res,
                    "geo_stats": geo_res,
                    "distance": geodesic((my_geo["lat"], my_geo["lon"]), (geo_res["lat"], geo_res["lon"])).miles
                }
            }
        )
        dist = geodesic((my_geo["lat"], my_geo["lon"]), (geo_res["lat"], geo_res["lon"])).miles
        if (dist != 0) :
            rttanddists.append([ping_res[2], dist])
    except KeyError: # in the case that an ip does not have geolocation
        server_infos.append({
                server['IP/HOST']: {
                    "ping_stats": ping_res,
                    "geo_stats": geo_res,
                    "distance": -1.0
                }
            }
        )

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

print(server_infos)
plot_1b(rttanddists)

"""
example of one output line:
{'chch.linetest.nz': {'ping_stats': (206.711, 207.856, 207.431), 'geo_stats': {'status': 'success', 'country': 'New Zealand', 'countryCode': 'NZ', 'region': 'WKO', 'regionName': 'Waikato Region', 'city': 'Paeroa', 'zip': '3600', 'lat': -37.3657, 'lon': 175.6716, 'timezone': 'Pacific/Auckland', 'isp': 'Two Degrees Mobile Limited', 'org': 'CallPlus Services Limited', 'as': 'AS9790 Two Degrees Networks Limited', 'query': '101.98.9.201'}, 'distance': 8155.153461010741}}

ping stats are in ms. if ping stats is a tuple of (-1, -1, -1), that means ping failed and you should probably ignore and not graph that one.
distance might also be -1, means that there was no valid geolocation result returned from the api, you should also maybe ignore and not graph that either. You likely don't need most of the data in geo_stats but it's all there in case you need to use it in graphing

The data from own IP is NOT included in the server_infos array because I thought that didn't really make much sense to do
"""
