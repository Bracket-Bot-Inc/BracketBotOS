import subprocess, json, socket, struct,time, concurrent.futures
from collections import defaultdict

def update_stats(writer_data, reader_data):
    def get_data(sock: str):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        res = s.connect_ex(f'\0{sock}')
        s.settimeout(1.0)
        data = None
        if res == 0:
            try:
                data = s.recv(1024)
            except socket.timeout:
                pass
        s.close()
        return data
    # This avoids duplicates that come from multiple entries per socket (e.g., connected endpoints)
    awk_prog = 'NR>1 && $6=="01" && $NF ~ /^@.*\.bbos$/ {sub(/^@/, "", $NF); print $NF}'
    result = subprocess.run(["awk", awk_prog, "/proc/net/unix"], capture_output=True, text=True)
    sockets = result.stdout.splitlines()
    writers = {sock.split("__")[0].replace(".bbos", "") for sock in sockets}
    def process_socket(sock):
        w = sock.split("__")[0].replace(".bbos", "")
        if "timelog" in sock:
            reader = f"{sock.split('__')[2]}/{sock.split('__')[1]}"
            data = get_data(sock)
            return ("timelog", w, reader, struct.unpack("<qqq", data) if data else None)
        else:
            data = get_data(sock)
            return ("writer", w, json.loads(data) if data else None)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = list(executor.map(process_socket, sockets))

    for result in results:
        if result[0] == "timelog":
            _, w, reader, data = result
            reader_data[w][reader] = data
        else:
            _, w, data = result
            writer_data[w] = data
    return writer_data, reader_data

def main():
    writer_data, reader_data = {}, defaultdict(dict)
    print("Collecting readers and writers...", flush=True)
    update_stats(writer_data, reader_data)
    for writer, info in writer_data.items():
        print(f"Writer : {writer}")
        if not info:
            print("  (No data)")
            print("-" * 40)
            continue
        print(f"  Caller : {info['caller']}")
        print(f"  Owner  : {info['owner']}")
        print(f"  Target Period: {info['period']} ms")
        print("  DType  :")
        for f in info['dtype']:
            if len(f) == 3:
                shape = tuple(f[2]) if isinstance(f[2], list) else (f[2],)
                print(f"    - {f[0]}: {f[1]}, shape={shape}")
            else:
                print(f"    - {f[0]}: {f[1]}")
        for reader, data in reader_data[writer].items():
            print(f"  Reader : {reader}")
            if data:
                avg_ms = data[0] / 1_000_000  # ns to ms
                std_ms = data[1] / 1_000_000  # ns to ms
                max_ms = data[2] / 1_000_000  # ns to ms
                print(f"    Data : avg={avg_ms:.2f}ms, std={std_ms:.2f}ms, max={max_ms:.2f}ms")
            else:
                print(f"    Data : None")
        print("-" * 40)

if __name__ == "__main__":
    main()