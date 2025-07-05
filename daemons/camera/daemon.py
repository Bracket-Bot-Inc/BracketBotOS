from bbos.shm import Writer
from bbos.registry import get_cfg, get_type
from bbos.time import Rate

import os, time, json, sys
import numpy as np
import fcntl
import select
import v4l2
import mmap
import ctypes
from turbojpeg import decompress, PF


def main():
    CFG = get_cfg("CFG_camera_stereo_OV9281")
    fd = os.open(f'/dev/video{CFG.dev}', os.O_RDWR)

    # Set format
    fmt = v4l2.v4l2_format()
    fmt.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
    fmt.fmt.pix.width = CFG.width
    fmt.fmt.pix.height = CFG.height
    fmt.fmt.pix.pixelformat = v4l2.V4L2_PIX_FMT_MJPEG
    fmt.fmt.pix.field = v4l2.V4L2_FIELD_NONE
    fcntl.ioctl(fd, v4l2.VIDIOC_S_FMT, fmt)

    # Set frame rate
    parm = v4l2.v4l2_streamparm()
    parm.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
    parm.parm.capture.timeperframe.numerator = 1
    parm.parm.capture.timeperframe.denominator = CFG.fps
    fcntl.ioctl(fd, v4l2.VIDIOC_S_PARM, parm)

    # Request buffers
    req = v4l2.v4l2_requestbuffers()
    req.count = 1
    req.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
    req.memory = v4l2.V4L2_MEMORY_MMAP
    fcntl.ioctl(fd, v4l2.VIDIOC_REQBUFS, req)

    # Query and mmap buffer
    buf = v4l2.v4l2_buffer()
    buf.index = 0
    buf.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
    buf.memory = v4l2.V4L2_MEMORY_MMAP
    fcntl.ioctl(fd, v4l2.VIDIOC_QUERYBUF, buf)

    mmap_buf = mmap.mmap(fd,
                         buf.length,
                         mmap.MAP_SHARED,
                         mmap.PROT_READ | mmap.PROT_WRITE,
                         offset=buf.m.offset)

    # Stream on
    buf_type = ctypes.c_int(v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE)
    fcntl.ioctl(fd, v4l2.VIDIOC_STREAMON, buf_type)

    r = Rate(CFG.fps)
    with Writer('/camera_stereo', get_type("camera_stereo_OV9281")) as w:
        while True:
            # Queue buffer
            fcntl.ioctl(fd, v4l2.VIDIOC_QBUF, buf)
            # Get raw MJPEG frame (zero-copy)
            # Wait for frame
            select.select([fd], [], [])
            # Dequeue buffer
            fcntl.ioctl(fd, v4l2.VIDIOC_DQBUF, buf)
            # Decode
            stereo = np.array(decompress(mmap_buf[:buf.bytesused], PF.RGB),
                              copy=False)
            w['stereo'] = stereo[::-1]
            r.tick()
    # Cleanup
    fcntl.ioctl(fd, v4l2.VIDIOC_STREAMOFF, buf_type)
    mmap_buf.close()
    os.close(fd)
    print(r.stats)


if __name__ == "__main__":
    main()
