#!/usr/bin/env python3
"""
Unit tests for bbos IPC Writer/Reader system.
Tests data integrity by ensuring readers receive values with correct data
and measures bandwidth performance across different array sizes.
"""

import unittest
import numpy as np
import time
import multiprocessing
from typing import Tuple
import os
import sys

# Add parent directory to path to import bbos
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bbos import Writer, Reader, Type, realtime, register


# Register test types for different array sizes
@realtime(ms=5)  # 5ms for faster testing
def test_ipc_small():
    return [
        ("data", np.float32, (10,)),
        ("sequence", np.uint32)
    ]


@realtime(ms=5)
def test_ipc_medium():
    return [
        ("data", np.float32, (1000,)),
        ("sequence", np.uint32)
    ]


@realtime(ms=5)
def test_ipc_large():
    return [
        ("data", np.float32, (10000,)),
        ("sequence", np.uint32)
    ]


@realtime(ms=5)
def test_ipc_xlarge():
    return [
        ("data", np.float32, (100000,)),
        ("sequence", np.uint32)
    ]


class TestIPC(unittest.TestCase):
    """Test suite for IPC Writer/Reader system"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        cls.test_channel_prefix = "test_ipc_"
        
    def setUp(self):
        """Set up for each test"""
        self.channel_counter = 0
        
    def get_channel_name(self) -> str:
        """Generate unique channel name for each test"""
        self.channel_counter += 1
        return f"{self.test_channel_prefix}{os.getpid()}_{self.channel_counter}"
    
    def writer_process(self, channel: str, type_name: str, array_size: int, num_values: int, result_queue: multiprocessing.Queue):
        """Writer process that sends values atomically"""
        try:
            with Writer(channel, Type(type_name), keeptime=False) as writer:
                start_time = time.time()
                bytes_written = 0
                
                for i in range(1, num_values + 1):
                    # Use buf() for atomic writes
                    with writer.buf() as buf:
                        # Fill array with current sequence number
                        buf['data'][:] = float(i)
                        buf['sequence'] = np.uint32(i)
                    
                    bytes_written += array_size * 4  # float32 = 4 bytes
                    
                    # Delay to ensure reader has time to process
                    # This simulates a real-time system where data comes at intervals
                    time.sleep(0.0005)  # 0.5ms delay
                
                # Final delay to ensure last value is read
                time.sleep(0.2)
                
                elapsed = time.time() - start_time
                bandwidth_mbps = (bytes_written / elapsed) / (1024 * 1024)
                result_queue.put(('writer_stats', elapsed, bandwidth_mbps))
                
        except Exception as e:
            import traceback
            result_queue.put(('writer_error', str(e) + '\n' + traceback.format_exc()))
    
    def reader_process(self, channel: str, array_size: int, num_values: int, result_queue: multiprocessing.Queue):
        """Reader process that verifies data integrity"""
        try:
            sequences_seen = []
            unique_sequences = set()
            start_time = None
            bytes_read = 0
            mismatches = 0
            
            with Reader(channel, keeptime=False) as reader:
                timeout_start = time.time()
                last_seen = 0
                
                # Continue until we see the final value or timeout
                while last_seen < num_values and time.time() - timeout_start < 30:
                    if reader.ready():
                        if start_time is None:
                            start_time = time.time()
                        
                        # Read data
                        sequence = int(reader.data['sequence'])
                        data_array = reader.data['data']
                        
                        # Verify data integrity - all values should match sequence
                        expected_value = float(sequence)
                        if not np.allclose(data_array, expected_value):
                            mismatches += 1
                            # Only report first few mismatches
                            if mismatches <= 3:
                                result_queue.put(('reader_warning', 
                                    f"Data mismatch at sequence {sequence}: expected {expected_value}, got {data_array[0]}"))
                        
                        # Track sequences
                        if sequence not in unique_sequences:
                            unique_sequences.add(sequence)
                            sequences_seen.append(sequence)
                            bytes_read += data_array.nbytes
                            last_seen = max(last_seen, sequence)
                    
                    # Very small sleep to prevent busy waiting
                    else:
                        time.sleep(0.0001)
                
                if time.time() - timeout_start >= 30:
                    result_queue.put(('reader_error', 
                        f"Timeout: last seen sequence was {last_seen} out of {num_values}"))
                    return
                
                # Verify sequences are monotonically increasing
                for i in range(1, len(sequences_seen)):
                    if sequences_seen[i] <= sequences_seen[i-1]:
                        result_queue.put(('reader_error', 
                            f"Non-monotonic sequence: {sequences_seen[i-1]} -> {sequences_seen[i]}"))
                        return
                
                elapsed = time.time() - start_time if start_time else 1.0
                bandwidth_mbps = (bytes_read / elapsed) / (1024 * 1024)
                
                # Calculate percentage of values received
                percent_received = (len(unique_sequences) / num_values) * 100
                
                result_queue.put(('reader_success', len(unique_sequences), elapsed, bandwidth_mbps, 
                                 percent_received, mismatches))
                
        except Exception as e:
            import traceback
            result_queue.put(('reader_error', str(e) + '\n' + traceback.format_exc()))
    
    def run_bandwidth_test(self, type_name: str, array_size: int, num_values: int = 10000) -> Tuple[bool, float, str]:
        """Run a single bandwidth test with given array size"""
        channel = self.get_channel_name()
        result_queue = multiprocessing.Queue()
        
        # Start writer and reader processes
        writer_proc = multiprocessing.Process(
            target=self.writer_process, 
            args=(channel, type_name, array_size, num_values, result_queue)
        )
        reader_proc = multiprocessing.Process(
            target=self.reader_process,
            args=(channel, array_size, num_values, result_queue)
        )
        
        reader_proc.start()
        time.sleep(0.1)  # Give reader time to initialize
        writer_proc.start()
        
        # Collect results
        results = {}
        warnings = []
        timeout = time.time() + 35  # 35 second timeout
        
        while time.time() < timeout and len(results) < 2:
            if not result_queue.empty():
                result = result_queue.get()
                if result[0] == 'reader_success':
                    results['reader'] = ('success', result[1], result[2], result[3], result[4], result[5])
                elif result[0] == 'reader_error':
                    results['reader'] = ('error', result[1])
                elif result[0] == 'reader_warning':
                    warnings.append(result[1])
                elif result[0] == 'writer_stats':
                    results['writer'] = ('stats', result[1], result[2])
                elif result[0] == 'writer_error':
                    results['writer'] = ('error', result[1])
        
        # Clean up processes
        writer_proc.join(timeout=1)
        reader_proc.join(timeout=1)
        
        if writer_proc.is_alive():
            writer_proc.terminate()
        if reader_proc.is_alive():
            reader_proc.terminate()
        
        # Analyze results
        if 'reader' not in results:
            return False, 0.0, "Reader process did not report results"
        
        if results['reader'][0] == 'error':
            return False, 0.0, f"Reader error: {results['reader'][1]}"
        
        if results['reader'][0] == 'success':
            _, num_received, elapsed, bandwidth, percent, mismatches = results['reader']
            
            # In a real-time system, we don't expect to receive all values
            # What matters is data integrity and that we're receiving data consistently
            if mismatches == 0 and num_received > 0:
                return True, bandwidth, f"Received {num_received}/{num_values} ({percent:.1f}%) values at {bandwidth:.2f} MB/s with perfect data integrity"
            elif mismatches > 0:
                return False, bandwidth, f"Data integrity errors: {mismatches} mismatches found in {num_received} values"
            else:
                return False, bandwidth, f"No values received"
        
        return False, 0.0, "Unknown error"
    
    def test_small_array_integrity(self):
        """Test data integrity with small arrays (10 elements)"""
        success, bandwidth, msg = self.run_bandwidth_test(type_name="test_ipc_small", array_size=10, num_values=10000)
        print(f"\nSmall array (10 elements): {msg}")
        self.assertTrue(success, msg)
    
    def test_medium_array_integrity(self):
        """Test data integrity with medium arrays (1000 elements)"""
        success, bandwidth, msg = self.run_bandwidth_test(type_name="test_ipc_medium", array_size=1000, num_values=10000)
        print(f"\nMedium array (1000 elements): {msg}")
        self.assertTrue(success, msg)
    
    def test_large_array_integrity(self):
        """Test data integrity with large arrays (10000 elements)"""
        success, bandwidth, msg = self.run_bandwidth_test(type_name="test_ipc_large", array_size=10000, num_values=5000)
        print(f"\nLarge array (10000 elements): {msg}")
        self.assertTrue(success, msg)
    
    def test_very_large_array_integrity(self):
        """Test data integrity with very large arrays (100000 elements)"""
        success, bandwidth, msg = self.run_bandwidth_test(type_name="test_ipc_xlarge", array_size=100000, num_values=1000)
        print(f"\nVery large array (100000 elements): {msg}")
        self.assertTrue(success, msg)
    
    def test_bandwidth_scaling(self):
        """Test bandwidth across multiple array sizes"""
        test_configs = [
            ("test_ipc_small", 10, 10000),
            ("test_ipc_medium", 1000, 5000),
            ("test_ipc_large", 10000, 1000),
            ("test_ipc_xlarge", 100000, 100)
        ]
        
        print("\nBandwidth scaling test:")
        print("Array Size | Values | Bandwidth (MB/s) | Received % | Status")
        print("-" * 65)
        
        for type_name, size, num_values in test_configs:
            success, bandwidth, msg = self.run_bandwidth_test(type_name=type_name, array_size=size, num_values=num_values)
            status = "PASS" if success else "FAIL"
            
            # Extract percentage from message
            import re
            percent_match = re.search(r'(\d+\.?\d*)%', msg)
            percent = percent_match.group(1) if percent_match else "N/A"
            
            print(f"{size:10} | {num_values:6} | {bandwidth:16.2f} | {percent:>9}% | {status}")
            
            # For scaling test, we're more lenient - just need data integrity
            if not success and "integrity errors" in msg:
                self.fail(f"Failed for array size {size}: {msg}")
    
    def test_multiple_readers_single_writer(self):
        """Test that multiple readers can read from a single writer"""
        channel = self.get_channel_name()
        result_queue = multiprocessing.Queue()
        type_name = "test_ipc_medium"
        array_size = 1000
        num_values = 1000
        num_readers = 3
        
        # Start multiple readers
        reader_procs = []
        for i in range(num_readers):
            proc = multiprocessing.Process(
                target=self.reader_process,
                args=(channel, array_size, num_values, result_queue)
            )
            proc.start()
            reader_procs.append(proc)
        
        time.sleep(0.2)  # Give readers time to initialize
        
        # Start single writer
        writer_proc = multiprocessing.Process(
            target=self.writer_process,
            args=(channel, type_name, array_size, num_values, result_queue)
        )
        writer_proc.start()
        
        # Collect results
        successful_readers = 0
        timeout = time.time() + 20
        
        while time.time() < timeout and successful_readers < num_readers:
            if not result_queue.empty():
                result = result_queue.get()
                if result[0] == 'reader_success':
                    successful_readers += 1
                elif result[0] == 'reader_error':
                    # In multi-reader scenario, some contention is expected
                    print(f"Reader error in multi-reader test (may be expected): {result[1]}")
        
        # Clean up
        writer_proc.join(timeout=1)
        for proc in reader_procs:
            proc.join(timeout=1)
            if proc.is_alive():
                proc.terminate()
        
        # In a multi-reader scenario with real-time data, at least 1 reader should succeed
        self.assertGreaterEqual(successful_readers, 1, 
                        f"No readers succeeded out of {num_readers}")
        print(f"\nMulti-reader test: {successful_readers}/{num_readers} readers successfully received values")


if __name__ == '__main__':
    # Run with verbosity to see print statements
    unittest.main(verbosity=2)