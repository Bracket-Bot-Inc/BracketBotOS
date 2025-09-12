#!/usr/bin/env python3
"""Debug script to understand IPC behavior"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bbos import Writer, Reader, Type, realtime
import numpy as np
import time

@realtime(ms=10)
def debug_type():
    return [
        ("data", np.float32, (5,)),
        ("sequence", np.uint32)
    ]

def test_simple():
    """Simple test to see what's happening"""
    print("Starting simple IPC test...")
    
    # Start writer in background
    import multiprocessing
    
    def writer_proc():
        with Writer("debug_channel", Type("debug_type"), keeptime=False) as w:
            for i in range(1, 11):
                data = np.full(5, float(i), dtype=np.float32)
                print(f"Writer: sending sequence {i} with data {data[0]}")
                w['data'] = data
                w['sequence'] = np.uint32(i)
                time.sleep(0.05)  # 50ms between writes
            time.sleep(0.2)  # Give reader time to catch up
    
    def reader_proc():
        with Reader("debug_channel", keeptime=False) as r:
            last_seq = 0
            timeout = time.time() + 2.0
            while time.time() < timeout:
                if r.ready():
                    seq = int(r.data['sequence'])
                    data_val = r.data['data'][0]
                    print(f"Reader: got sequence {seq} with data {data_val}")
                    
                    if data_val != float(seq):
                        print(f"ERROR: Mismatch! sequence={seq}, data={data_val}")
                    
                    if seq <= last_seq:
                        print(f"ERROR: Non-monotonic! last={last_seq}, current={seq}")
                    
                    last_seq = seq
                time.sleep(0.001)
    
    # Run test
    wp = multiprocessing.Process(target=writer_proc)
    rp = multiprocessing.Process(target=reader_proc)
    
    rp.start()
    time.sleep(0.1)
    wp.start()
    
    wp.join()
    rp.join()

if __name__ == "__main__":
    test_simple()




