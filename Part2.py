import json
import random
import platform
import re
import subprocess
import matplotlib.pyplot as plt

# Verify that the json file is desired not just a literal list of IPs
IP_FILE = "data\\listed_iperf3_servers.json"
NUM_DESTINATIONS = 5

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

    result = subprocess.run(command, capture_output=True, text=True, timeout=150)
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
    Shoutout chatgpt i didnt think of thi
    Example:
        10 ms -> 10 ms
        17 ms ->  7 ms
        25 ms ->  8 ms
    """

    result = []
    previous = 0

    for hop, rtt in hops:
        latency = max(0, rtt - previous)
        result.append((hop, latency))
        previous = rtt

    return result


def plot_results(results):
    destinations = list(results.keys())
    fig, ax = plt.subplots(figsize=(12, 7))
    bottoms = [0] * len(destinations)
    max_hops = max(len(hops) for hops in results.values())

    for hop_index in range(max_hops):
        values = []

        for destination in destinations:
            hops = results[destination]
            if hop_index < len(hops):
                values.append(hops[hop_index][1])
            else:
                values.append(0)

        ax.bar(destinations, values, bottom=bottoms, label=f"Hop {hop_index + 1}")
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


def main():
    destinations = load_destinations(IP_FILE)

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

        try:
            hops = traceroute(destination)

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
    plot_results(results)


if __name__ == "__main__":
    main()