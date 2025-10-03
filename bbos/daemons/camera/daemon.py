from bbos import Writer, Config, Type
import os, fcntl, select, v4l2, mmap, ctypes, time
import numpy as np
import cv2

def xioctl(fd, req, arg):
    while True:
        try:
            return fcntl.ioctl(fd, req, arg)
        except InterruptedError:
            continue

def main():
    CFG = Config("stereo")
    fd = os.open(f"/dev/video{CFG.dev}", os.O_RDWR | os.O_NONBLOCK)

    # --- Set format ---
    fmt = v4l2.v4l2_format()
    fmt.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
    fmt.fmt.pix.width = CFG.width
    fmt.fmt.pix.height = CFG.height
    fmt.fmt.pix.pixelformat = v4l2.V4L2_PIX_FMT_YUYV if CFG.fmt == "YUYV" else v4l2.V4L2_PIX_FMT_MJPEG
    fmt.fmt.pix.field = v4l2.V4L2_FIELD_NONE
    xioctl(fd, v4l2.VIDIOC_S_FMT, fmt)

    # --- Set FPS ---
    parm = v4l2.v4l2_streamparm()
    parm.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
    parm.parm.capture.timeperframe.numerator = 1
    parm.parm.capture.timeperframe.denominator = CFG.rate
    xioctl(fd, v4l2.VIDIOC_S_PARM, parm)

    # --- Request multiple MMAP buffers ---
    NUM_BUFS = 4
    req = v4l2.v4l2_requestbuffers()
    req.count = NUM_BUFS
    req.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
    req.memory = v4l2.V4L2_MEMORY_MMAP
    xioctl(fd, v4l2.VIDIOC_REQBUFS, req)
    if req.count < 2:
        raise RuntimeError("Driver could not provide >=2 MMAP buffers")

    # --- Query + mmap each buffer ---
    mmaps = []
    for i in range(req.count):
        buf = v4l2.v4l2_buffer()
        buf.index = i
        buf.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        buf.memory = v4l2.V4L2_MEMORY_MMAP
        xioctl(fd, v4l2.VIDIOC_QUERYBUF, buf)

        mm = mmap.mmap(fd, buf.length, mmap.MAP_SHARED,
                       mmap.PROT_READ | mmap.PROT_WRITE, offset=buf.m.offset)
        mmaps.append((mm, buf.length))

    # --- Queue all buffers before STREAMON ---
    for i in range(req.count):
        buf = v4l2.v4l2_buffer()
        buf.index = i
        buf.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        buf.memory = v4l2.V4L2_MEMORY_MMAP
        xioctl(fd, v4l2.VIDIOC_QBUF, buf)

    # --- STREAMON ---
    buf_type = ctypes.c_int(v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE)
    xioctl(fd, v4l2.VIDIOC_STREAMON, buf_type)

    poller = select.poll()
    poller.register(fd, select.POLLIN)

    t_last = time.monotonic()
    frame_count = 0

    if CFG.fmt == "YUYV":
        with Writer("camera.rgb", Type("camera_rgb"), buf_ms=10000) as w:
            while True:
                # Wait for a frame
                poller.poll(1000)  # ms timeout
                # Dequeue ready buffer
                buf = v4l2.v4l2_buffer()
                buf.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
                buf.memory = v4l2.V4L2_MEMORY_MMAP
                xioctl(fd, v4l2.VIDIOC_DQBUF, buf)

                mm, _ = mmaps[buf.index]
                mv = memoryview(mm)

                # (Optional) latency metric
                now = time.monotonic()
                dt = now - t_last
                t_last = now
                frame_count += 1
                if (frame_count & 0x1F) == 0:  # print every 32 frames
                    print(f"{dt:.6f}s")

                # Convert YUYV to RGB (h,w,3)
                yuyv_data = np.frombuffer(mv[:buf.bytesused], dtype=np.uint8)
                yuyv_img = yuyv_data.reshape((CFG.height, CFG.width, 2))
                rgb_img = cv2.cvtColor(yuyv_img, cv2.COLOR_YUV2RGB_YUYV)
                
                # Write RGB data
                with w.buf() as b:
                    b["rgb"][:] = rgb_img

                # Re-queue the same buffer for reuse
                xioctl(fd, v4l2.VIDIOC_QBUF, buf)
    elif CFG.fmt == "MJPEG":
        with Writer("camera.rgb", Type("camera_rgb"), buf_ms=1000) as w:
            t0 = time.monotonic()
            while True:
                # Wait for a frame
                poller.poll(1000)  # ms timeout
                # Dequeue ready buffer
                buf = v4l2.v4l2_buffer()
                buf.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
                buf.memory = v4l2.V4L2_MEMORY_MMAP
                xioctl(fd, v4l2.VIDIOC_DQBUF, buf)

                mm, _ = mmaps[buf.index]
                mv = memoryview(mm)
                now = time.time_ns()
                # Copy into Writer buffer (zero-copy if your Writer supports it)
                img = cv2.imdecode(np.array(mv[:buf.bytesused]), cv2.IMREAD_COLOR)
                with w.buf() as b:
                    b["rgb"][:buf.bytesused] = img
                    b["timestamp"] = np.datetime64(now, 'ns')
                print(f"{time.monotonic() - t0:.6f}s", flush=True)
                t0 = time.monotonic()

                # Re-queue the same buffer for reuse
                xioctl(fd, v4l2.VIDIOC_QBUF, buf)

    # --- STREAMOFF / cleanup (unreached in this example) ---
    xioctl(fd, v4l2.VIDIOC_STREAMOFF, buf_type)
    for mm, _ in mmaps:
        mm.close()
    os.close(fd)

if __name__ == "__main__":
    main()
