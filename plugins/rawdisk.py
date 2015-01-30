#!/usr/bin/python -tt
# vim:set ts=4 sw=4 expandtab:
#
# NodeManager plugin to support mapping unused raw disks into a slice
# that has the rawdisk sliver tag

"""
Raw disk support for NodeManager.

Copies all unused devices into slices with the rawdisk attribute set.
"""

import errno
import os
import time
import re

import logger
import tools

def start():
    logger.log("rawdisk: plugin starting up...")

def get_unused_devices():
    devices = []
    if os.path.exists("/dev/mapper/planetlab-rawdisk"):
        devices.append("/dev/mapper/planetlab-rawdisk")
    # Figure out which partitions are part of the VG
    in_vg = []
    for i in os.listdir("/sys/block"):
        if not i.startswith("dm-"):
            continue
        in_vg.extend(map(lambda x: x.replace("!", "/"),
                         os.listdir("/sys/block/%s/slaves" % i)))
    # Read the list of partitions
    partitions = file("/proc/partitions", "r")
    pat = re.compile("\s+")
    while True:
        buf = partitions.readline()
        if buf == "":
            break
        buf = buf.strip()
        fields = re.split(pat, buf)
        dev = fields[-1]
        if (not dev.startswith("dm-") and dev not in in_vg and
            os.path.exists("/dev/%s" % dev) and
            (os.minor(os.stat("/dev/%s" % dev).st_rdev) % 2) != 0):
            devices.append("/dev/%s" % dev)
    partitions.close()
    return devices

def GetSlivers(data, config=None, plc=None):
    if 'slivers' not in data:
        logger.log_missing_data("rawdisk.GetSlivers",'slivers')
        return

    devices = get_unused_devices()
    for sliver in data['slivers']:
        for attribute in sliver['attributes']:
            name = attribute.get('tagname',attribute.get('name',''))
            if name == 'rawdisk':
                for i in devices:
                    st = os.stat(i)
                    path = "/vservers/%s%s" % (sliver['name'], i)
                    if os.path.exists(path):
                        # should check whether its the proper type of device
                        continue

                    logger.log("rawdisk: Copying %s to %s" % (i, path))
                    try:
                        if os.path.exists(path):
                            os.unlink(path)
                    except:
                        pass
                    try:
                        os.makedirs(os.path.dirname(path), 0755)
                    except:
                        pass
                    os.mknod(path, st.st_mode, st.st_rdev)
