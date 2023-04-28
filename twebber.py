import sys
import logging
import json
import time
from os.path import dirname, exists, realpath
from os import makedirs


LOG = logging.getLogger()


class ANLog:
    def __init__(self, asciinfo, fh):
        self.fh = fh
        self.start_ts = asciinfo['timestamp']
        self.curr_ts = 0.0
        self.last_frame_ts = 0.0
        self.frame = None

    def start(self, ref_ts):
        self.start_ts = float(ref_ts)
        line = self.fh.readline()
        self.frame = json.loads(line)
        self.curr_ts = self.start_ts + self.frame[0]

    def skip_to(self, stop_ts):
        while self.curr_ts < stop_ts:
            self.last_frame_ts = self.frame[0]
            line = self.fh.readline()
            if line:
                self.frame = json.loads(line)
                self.curr_ts = self.start_ts + self.frame[0]
            else:
                self.curr_ts = float('Infinity')
        return self.last_frame_ts


class Hops:
    LEFT = 'left'
    RIGHT = 'right'

    def __init__(self, start_at):
        self.active = start_at
        self.hops_from_left = []
        self.hops_from_right = []

    def hop(self, from_ts, to_ts):
        if self.active == Hops.LEFT:
            self.hops_from_left.append((from_ts, to_ts))
            self.active = Hops.RIGHT
        else:
            self.hops_from_right.append((from_ts, to_ts))
            self.active = Hops.LEFT


def parse(leftfile, rightfile):
    line = leftfile.readline()
    asciinfo = json.loads(line)
    if not asciinfo.get('version') == 2:
        print("First asciinema file is not a version 2 recording. Cannot parse this file.")
        exit()
    left = ANLog(asciinfo, leftfile)

    line = rightfile.readline()
    asciinfo = json.loads(line)
    if not asciinfo.get('version') == 2:
        print("Second asciinema file is not a version 2 recording. Cannot parse this file.")
        exit()
    right = ANLog(asciinfo, rightfile)

    t = time.localtime(left.curr_ts)
    LOG.info("Left starts at  %d, %d:%d:%d", left.curr_ts, t.tm_hour, t.tm_min, t.tm_sec)
    t = time.localtime(right.curr_ts)
    LOG.info("Right starts at %d, %d:%d:%d", right.curr_ts, t.tm_hour, t.tm_min, t.tm_sec)

    hops = None
    diff = right.start_ts - left.start_ts
    active = paused = None
    if diff >= 0:
        active = left
        left.start(0)
        paused = right
        right.start(diff)
        hops = Hops(Hops.LEFT)
    else:
        active = right
        right.start(0)
        paused = left
        left.start(-diff)
        hops = Hops(Hops.RIGHT)

    LOG.debug("Active frame is at %f", active.curr_ts)
    LOG.debug("Paused frame is at %f", paused.curr_ts)
    LOG.info("Starting at %s", "left" if active == left else "right")
    while True:
        from_ts = active.skip_to(paused.curr_ts)
        if active.curr_ts == float('inf') and paused.curr_ts == float('inf'):
            LOG.info("Ending on %s side with last timestamp at %f", "left" if active == left else "right", from_ts)
            break;
        LOG.debug("Switching from %s at %f to %s at %f", "left" if active == left else "right", from_ts, "left" if paused == left else "right", paused.frame[0])
        hops.hop(from_ts, paused.frame[0])
        (active, paused) = (paused, active)


    return hops


def main():
    if len(sys.argv) <= 2:
        print("Asciinema file missing. Specify session files to parse.")
        exit()

    elif len(sys.argv) <= 3:
        with open(sys.argv[1], mode="r", encoding="utf-8") as leftfile, \
             open(sys.argv[2], mode="r", encoding="utf-8") as rightfile:
            LOG.info("twebber:: Parsing files %s and %s", sys.argv[1], sys.argv[2])
            hops = parse(leftfile, rightfile)

    else:
        if not exists(dirname(sys.argv[3])):
            makedirs(dirname(sys.argv[3]))
        with open(sys.argv[1], mode="r", encoding="utf-8") as leftfile, \
                open(sys.argv[2], mode="r", encoding="utf-8") as rightfile, \
                open(sys.argv[2], mode='w', encoding="utf-8") as destfile:
            LOG.info("PlainOut:: Parsing files %s and %s to %s", sys.argv[1], sys.argv[2], sys.argv[3])
            hops = parse(leftfile, rightfile)




if __name__ == '__main__':
    LOG_FORMAT = "%(levelname)s :%(module)s - %(message)s"
    logging.basicConfig(filename="twebber.log",
                        level=logging.DEBUG,
                        format=LOG_FORMAT,
                        filemode='w')
    main()
