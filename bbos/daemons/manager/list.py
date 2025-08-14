import subprocess, json, socket

def get_data(sock: str):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    res = s.connect_ex(f'\0{sock}')
    s.settimeout(0.1)
    data = None
    if res == 0:
        try:
            data = s.recv(1024)
        except socket.timeout:
            pass
    s.close()
    return data

# Use /proc/net/unix and pick only LISTEN state (St==01), abstract names ending in .bbos
# This avoids duplicates that come from multiple entries per socket (e.g., connected endpoints)
awk_prog = 'NR>1 && $6=="01" && $NF ~ /^@.*\.bbos$/ {sub(/^@/, "", $NF); print $NF}'
result = subprocess.run(["awk", awk_prog, "/proc/net/unix"], capture_output=True, text=True)
sockets = result.stdout.splitlines()
writers = {sock.split("__")[0].replace(".bbos", "") for sock in sockets}
reader_data = {w: [] for w in writers}
writer_data = {}

import concurrent.futures

def process_socket(sock):
    w = sock.split("__")[0].replace(".bbos", "")
    if "timelog" in sock:
        reader = f"{sock.split('__')[2]}/{sock.split('__')[1]}"
        return ("timelog", w, reader, get_data(sock))
    else:
        data = get_data(sock)
        return ("writer", w, json.loads(data) if data else None)

with concurrent.futures.ThreadPoolExecutor() as executor:
    results = list(executor.map(process_socket, sockets))

for result in results:
    if result[0] == "timelog":
        _, w, reader, data = result
        reader_data[w].append((reader, data))
    else:
        _, w, data = result
        writer_data[w] = data

for writer, info in writer_data.items():
    print(f"Writer : {writer}")
    if not info:
        print("  (No data)")
        print("-" * 40)
        continue
    print(f"  Caller : {info['caller']}")
    print(f"  Owner  : {info['owner']}")
    print(f"  Target Latency: {info['latency']} ms")
    print("  DType  :")
    for f in info['dtype']:
        if len(f) == 3:
            shape = tuple(f[2]) if isinstance(f[2], list) else (f[2],)
            print(f"    - {f[0]}: {f[1]}, shape={shape}")
        else:
            print(f"    - {f[0]}: {f[1]}")
    print("-" * 40)
