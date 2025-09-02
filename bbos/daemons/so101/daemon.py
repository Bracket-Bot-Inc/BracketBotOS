from bbos import Reader, Writer, Config, Type
import scservo_sdk as scs
import numpy as np
import time

CFG = Config('so101')

# http://doc.feetech.cn/#/prodinfodownload?srcType=FT-SCSCL-emanual-cbcc8ab2e3384282a01d4bf3
FIRMWARE_MAJOR_VERSION = (0, 1)
FIRMWARE_MINOR_VERSION = (1, 1)
MODEL_NUMBER = (3, 2)
PROTOCOL = 0

SCS_SERIES_CONTROL_TABLE = {
    # EPROM
    "Firmware_Major_Version": FIRMWARE_MAJOR_VERSION,  # read-only
    "Firmware_Minor_Version": FIRMWARE_MINOR_VERSION,  # read-only
    "Model_Number": MODEL_NUMBER,  # read-only
    "ID": (5, 1),
    "Baud_Rate": (6, 1),
    "Return_Delay_Time": (7, 1),
    "Response_Status_Level": (8, 1),
    "Min_Position_Limit": (9, 2),
    "Max_Position_Limit": (11, 2),
    "Max_Temperature_Limit": (13, 1),
    "Max_Voltage_Limit": (14, 1),
    "Min_Voltage_Limit": (15, 1),
    "Max_Torque_Limit": (16, 2),
    "Phase": (18, 1),
    "Unloading_Condition": (19, 1),
    "LED_Also101_Condition": (20, 1),
    "P_Coefficient": (21, 1),
    "D_Coefficient": (22, 1),
    "I_Coefficient": (23, 1),
    "Minimum_Startup_Force": (24, 2),
    "CW_Dead_Zone": (26, 1),
    "CCW_Dead_Zone": (27, 1),
    "Protective_Torque": (37, 1),
    "Protection_Time": (38, 1),
    # SRAM
    "Torque_Enable": (40, 1),
    "Acceleration": (41, 1),
    "Goal_Position": (42, 2),
    "Running_Time": (44, 2),
    "Goal_Velocity": (46, 2),
    "Lock": (48, 1),
    "Present_Position": (56, 2),  # read-only
    "Present_Velocity": (58, 2),  # read-only
    "Present_Load": (60, 2),  # read-only
    "Present_Voltage": (62, 1),  # read-only
    "Present_Temperature": (63, 1),  # read-only
    "Sync_Write_Flag": (64, 1),  # read-only
    "Status": (65, 1),  # read-only
    "Moving": (66, 1),  # read-only
    # Factory
    "PWM_Maximum_Step": (78, 1),
    "Moving_Velocity_Threshold*50": (79, 1),
    "DTs": (80, 1),  # (ms)
    "Minimum_Velocity_Limit*50": (81, 1),
    "Maximum_Velocity_Limit*50": (82, 1),
    "Acceleration_2": (83, 1),  # don't know what that is
}

WRITE_FUNC_TABLE = {
    "Goal_Position": lambda x: np.round(x * 4096).astype(np.uint16),
    "Goal_Velocity": lambda x: np.round(x * 1000).astype(np.uint16),
}

READ_FUNC_TABLE = {
    # raw counts -> continuous turns
    "Present_Position": lambda x: (np.asarray(x) % 4096) / 4096,
}

def pos_accum(p, pi, turns):
    p = np.asarray(p)
    dx = p - pi
    step = np.where(
        dx < -0.5,
        1,  # crossed 1→0 (forward)
        np.where(dx > 0.5, -1, 0))  # crossed 0→1 (reverse)

    turns += step  # accumulate full turns
    pi = p  # advance reference

    return p + turns  # unwrapped position

def init_so101():
    """Initialize so101 connection and configure motors"""
    port = scs.PortHandler(CFG.port)
    packet = scs.PacketHandler(PROTOCOL)
    
    print(f"Connecting to {CFG.port} at {CFG.baudrate} baud")
    
    if not port.openPort():
        raise RuntimeError(f"Failed to open {CFG.port}")
    if not port.setBaudRate(CFG.baudrate):
        raise RuntimeError("Failed to set baudrate")
    
    print(f"Connected to {CFG.port} at {CFG.baudrate} baud")
    
    # Verify all motors are connected
    connected_motors = []
    for sid in CFG.motors:
        model, comm, err = packet.ping(port, sid)
        if comm == scs.COMM_SUCCESS:
            print(f"ID {sid}: Model={model}, Error={err}")
            connected_motors.append(sid)
        else:
            print(f"ID {sid}: No response ({packet.getTxRxResult(comm)})")
    
    if len(connected_motors) != len(CFG.motors):
        missing = set(CFG.motors) - set(connected_motors)
        raise RuntimeError(f"Motors not found: {missing}")
    
    # Configure motors for optimal performance
    print("Configuring motors...")
    for sid in CFG.motors:
        # Set return delay time to 2µs (value of 0) for faster response
        comm, err = packet.write1ByteTxRx(port, sid, SCS_SERIES_CONTROL_TABLE["Return_Delay_Time"][0], 0)
        if comm != scs.COMM_SUCCESS:
            print(f"Failed to set return delay for motor {sid}: {packet.getTxRxResult(comm)}")
        
        # Set acceleration to 254 for faster movement
        comm, err = packet.write1ByteTxRx(port, sid, SCS_SERIES_CONTROL_TABLE["Acceleration"][0], 254)
        if comm != scs.COMM_SUCCESS:
            print(f"Failed to set acceleration for motor {sid}: {packet.getTxRxResult(comm)}")
    
    print("so101 initialization complete")
    return port, packet

def write_motors(port, packet, register_name, values):
    """Write values to a specific register on all motors using group sync write"""
    if len(values) != len(CFG.motors):
        raise ValueError(f"Values array length ({len(values)}) must match motor_ids length ({len(CFG.motors)})")
    
    # Apply write function if available
    if register_name in WRITE_FUNC_TABLE:
        values = WRITE_FUNC_TABLE[register_name](values)
    
    # Get register address and data length from control table
    register_addr = SCS_SERIES_CONTROL_TABLE[register_name][0]
    data_length = SCS_SERIES_CONTROL_TABLE[register_name][1]
    
    group_sync_write = scs.GroupSyncWrite(port, packet, register_addr, data_length)
    
    # Add data for each motor
    for i, sid in enumerate(CFG.motors):
        value = int(values[i])
        
        if data_length == 1:
            # 1-byte register
            data = [value & 0xFF]
        elif data_length == 2:
            # 2-byte register (little-endian)
            data = [scs.SCS_LOBYTE(value), scs.SCS_HIBYTE(value)]
        else:
            raise ValueError(f"Unsupported data length: {data_length}")
        
        group_sync_write.addParam(sid, data)
    
    # Execute group write
    group_sync_write.txPacket()
    group_sync_write.clearParam()
    return True


def read_motors(port, packet, register_name, result_array):
    """Read a specific register from all motors using group sync read"""
    
    # Get register address and data length from control table
    register_addr = SCS_SERIES_CONTROL_TABLE[register_name][0]
    data_length = SCS_SERIES_CONTROL_TABLE[register_name][1]
    func = READ_FUNC_TABLE[register_name] if register_name in READ_FUNC_TABLE else None
    
    group_sync_read = scs.GroupSyncRead(port, packet, register_addr, data_length)
    
    # Add all motors to group read
    for sid in CFG.motors:
        group_sync_read.addParam(sid)
    
    # Execute group read
    comm = group_sync_read.txRxPacket()
    if comm != scs.COMM_SUCCESS:
        print(f"Group sync read failed: {packet.getTxRxResult(comm)}")
        return
    
    # Extract data for each motor
    for i, sid in enumerate(CFG.motors):
        if group_sync_read.isAvailable(sid, register_addr, data_length):
            data = group_sync_read.getData(sid, register_addr, data_length)
            result_array[i] = float(data)
        else:
            result_array[i] = np.nan
    
    # Apply vectorized function to all results if provided
    if func:
        result_array[:] = func(result_array)
    
    group_sync_read.clearParam()

if __name__ == "__main__":
    port, packet = init_so101()
    with Writer("so101.state", Type("so101_state")) as w_state, \
        Reader("so101.torque", keeptime=False) as r_torque, \
        Reader("so101.ctrl") as r_ctrl:
        state = np.zeros((3, len(CFG.motors)), dtype=np.float32)
        t3 = time.monotonic()
        ps = np.zeros(len(CFG.motors), dtype=np.float32)
        ps_acc = np.zeros(len(CFG.motors), dtype=np.float32)
        ps0 = np.zeros(len(CFG.motors), dtype=np.float32)
        read_motors(port, packet, "Present_Position", ps0)
        print(ps0)
        vs = np.zeros(len(CFG.motors), dtype=np.float32)
        ts = np.zeros(len(CFG.motors), dtype=np.float32)
        t = time.monotonic()
        while True:
            if r_torque.ready():
                print(r_torque.data['enable'], flush=True)
                write_motors(port, packet, "Torque_Enable", r_torque.data['enable'])
            if r_ctrl.ready():
                #print(ps0 + r_ctrl.data['pos'])
                write_motors(port, packet, "Goal_Position", ps0 + r_ctrl.data['pos'])
                #write_motors(port, packet, "Goal_Velocity", r_ctrl['vel'])
            if w_state._update():
                ps_i = ps.copy()
                read_motors(port, packet, "Present_Position", ps)
                ps = ps - ps0
                ps_acc = pos_accum(ps, ps_i, np.trunc(ps_acc).astype(int))
                #read_motors(port, packet, "Present_Velocity", vs)
                #read_motors(port, packet, "Present_Load", ts)
                t = time.monotonic()
            with w_state.buf() as b:
                b['pos'] = ps_acc
                b['vel'] = vs
                b['torque'] = ts
    port.closePort()