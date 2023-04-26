import logging
import sys
import copy
import shutil
import json
import base64
import re
from os.path import dirname, exists
from os import makedirs

from terminal2html import VT2Html, HtmlDocumentCreator as VT2HtmlDocCreator
from terminalparser import TermLogParser
from vtparser import VT500Parser


LOG = logging.getLogger()


ACP_DIR = "js"


class HtmlDocumentCreator(VT2HtmlDocCreator):
    """
    HTML document creator that can add asciinema recordings for vim sessions
    """

    STYLE_DROPDOWN = """
  <style type="text/css">
    /* *** Dropdown for asciinema sessions *** */
    
    .vim-session { font-family: monospace; }

    .vimsession-dropdown { position: relative; top: -6ex; margin-bottom: -6ex; }
    .vimsession-dropdown > summary { cursor:pointer; color: #e6e6ff; }
    .vimsession-player-wrapper { display: flex; flex-wrap: wrap; margin-left: 1em; margin-top: 18px; }
    .controls-help { white-space: pre-wrap; font-family: monospace; }
    .vimsession-dump { display: none }
  </style>
"""

    STYLE_ASCIINEMA = """
<link rel="stylesheet" type="text/css" href="{acpdir}/asciinema-player.css" />
"""

    SCRIPT_ASCIINEMA = """
<script src="{acpdir}/asciinema-player.js"></script>
"""


    def __init__(self, out_fh=sys.stdout, palette="MyDracula", dark_bg=True, title=None, chapters={}, cmd_filter=[], hopto=None):
        super().HEAD_ELEMS.extend([self.STYLE_DROPDOWN,
                                   self.STYLE_ASCIINEMA.format(acpdir=ACP_DIR),
                                   self.SCRIPT_ASCIINEMA.format(acpdir=ACP_DIR) ])
        super().__init__(out_fh, palette, dark_bg, title, chapters, cmd_filter, hopto)
        self.ddcount = 0
        self.vimsessions = {}


    def vim_session(self, vimsession=None):
        if self.output_suppressed:
            return
        self.end_cmd_block()

        self.fh.write('      <details class="vimsession-dropdown">\n')
        self.fh.write('        <summary><span class="vim-session">  [==-- Vim editor session --==]</span></summary>\n')
        self.fh.write('        <div class="vimsession-player-wrapper">\n')
        if vimsession is not None:
            acbase64 = base64.b64encode(vimsession.encode("utf-8"))
            self.fh.write('          <div>\n')
            self.fh.write('            <asciinema-player idle-time-limit="3" src="data:application/json;base64,' + acbase64.decode("ascii") + '" />\n')
            self.fh.write('          </div>\n')
            self.fh.write('          <div class="controls-help">\n')
            self.fh.write('  Controls: \n')
            self.fh.write('    space       - play / pause \n')
            self.fh.write('    < / >       - de- / increase playback speed\n')
            self.fh.write('    ← / →       - rewind / fast-forward 5 seconds\n')
            self.fh.write('    0, 1, ... 9 - jump to 0%, 10%, ... 90%\n')
            self.fh.write('          </div>\n')
            self.fh.write('          <pre class="vimsession-dump">[\n')
            self.fh.write(vimsession + '\n')
            self.fh.write(']         </pre>\n')
        else:
            self.fh.write('          <span class="vim-session">     [==-- THIS SHOULD BE A DROPDOWN ASCIINEMA RECORDING --==]</span>\n')
        self.fh.write('        </div>\n')
        self.fh.write('      </details>\n')
        self.ddcount += 1

        self.start_cmd_block()


class VimRecording:
    """
    Recording a Vim session in a asciinema recording
    """
    def __init__(self, asciinfo):
        self.asciinfo = asciinfo

    def start(self, start_ts, height = -1):
        self.last_ts = start_ts
        self.height = height
        if (height >= 0):
            LOG.debug("VimRecording:: Start vim recording at ts %s with height %s", start_ts, height)
            asciinfo = copy.deepcopy(self.asciinfo)
            asciinfo["height"] = height
        else:
            LOG.debug("VimRecording:: Start vim recording at ts %s with default height %s", start_ts, self.asciinfo["height"])
            asciinfo = self.asciinfo
        LOG.debug("VimRecording:: asciinfo: '%s'", json.dumps(asciinfo))
        self.frames = [asciinfo]
        self.frames.append([0.0000, "o", "Start at " + str(start_ts) + "\r\n"])

    def quantize_ts(self, ts):
        for qstep in [4.0, 2.0, 1.0, 0.5, 0.3, 0.18, 0.1, 0.03]:
            if ts >= qstep:
                return qstep
        return ts

    def frame_time(self, ts):
        # Time relative to previously seen frame
        ts_diff = ts - self.last_ts
        # Quantize time span
        ts_diff = self.quantize_ts(ts_diff)
        # Timestamp of last saved frame
        ts_prev = self.frames[-1][0] if len(self.frames) > 1 else 0.0
        # New timestamp relative to last one
        rel_ts = ts_prev + ts_diff
        # Save seen frame time
        self.last_ts = ts
        return round(rel_ts, 5)

    def add(self, frame):
        LOG.debug("VimRecording:: Add frame at ts %s", frame[0])
        self.frames.append([self.frame_time(frame[0]), frame[1], frame[2]])

    def addall(self, frames):
        LOG.debug("VimRecording:: Add frames at ts %s - %s", frames[0][0], frames[-1][0])
        for f in frames:
            self.frames.append([self.frame_time(f[0]), f[1], f[2]])

    def to_string(self):
        return '\n'.join(json.dumps(f) for f in self.frames)


class Asciinema2Html(VT2Html, VT500Parser.DefaultTerminalOutputHandler, VT500Parser.DefaultControlSequenceHandler,
                     TermLogParser.DefaultEventListener):
    """
    Output class that writes the console session log to HTML format, recreating coloring, etc.

    Vim sessions are suppressed. In a later instance they could be added as asciinema inserts.
    """

    def __init__(self, asciinfo, parser, document=None):
        super().__init__(document)
        self.asciinfo = asciinfo
        self.parser = parser
        self.byteline = bytearray()
        self.framebuffer = []
        self.capturing_vim = False
        self.vimrecording = VimRecording(asciinfo)
        self.re_vim_end_1 = re.compile(TermLogParser.RE_VIM_END_1)
        self.re_vim_end_2 = re.compile(TermLogParser.RE_VIM_END_2)


    def parse(self, line):
        frame = json.loads(line)
        termline = frame[2].encode('utf-8')

        if self.in_vim:
            if self.capturing_vim:
                # Check if this frame includes the ending of the vim session.
                # If so, we end the capturing here without this and following frames,
                # so that our session replay doesn't close the vim secondary screen buffer.
                # Otherwise we include this frame in our session recording.
                match = self.re_vim_end_1.search(termline, re.MULTILINE)
                if not match:
                    match = self.re_vim_end_2.search(termline, re.MULTILINE)
                if match:
                    self.capturing_vim = False
                else:
                    self.vimrecording.add(frame)

        else:
            # Collect asciinema frames in a buffer until a newline appears
            # This is necessary to catch all frames leading up to a Vim session,
            # since the start may be spread over multiple frames without a newline showing up
            self.framebuffer.append(frame)

        for c in termline:
            self.byteline.append(c)
            if c == 0x0A:
                self.parser.parse(self.byteline)
                self.byteline.clear()
                self.framebuffer.clear()


    def vim_start(self):
        self.in_vim = True
        # Start a new vim session as asciinema recording
        self.capturing_vim = True
        # This needs to be timed relative to the timestamp from the frame that started the vim session
        self.vimrecording.start(self.framebuffer[0][0])
        self.vimrecording.addall(self.framebuffer)


    def vim_end(self):
        self.in_vim = False
        self.capturing_vim = False  # Just in case
        self.document.vim_session(self.vimrecording.to_string())



def parse(logfile, destfile=None, palette='MyDracula', title=None, chapters={}, cmd_filter=[], hopto=None):
    """Read the input file byte by byte and output as HTML, either to a file or to stdout."""

    line = logfile.readline()
    asciinfo = json.loads(line)
    if not asciinfo.get('version') == 2:
        print("Asciinema file is not a version 2 recording. Cannot parse this file.")
        exit()

    html = HtmlDocumentCreator(destfile, palette=palette, title=title, chapters=chapters, cmd_filter=cmd_filter, hopto=hopto)
    parser = TermLogParser()
    reader = Asciinema2Html(asciinfo, parser, html)

    parser.terminal_output_handler = reader
    parser.control_sequence_handler = reader
    parser.tlp_event_listener = reader

    line_no = 1
    line = logfile.readline()
    while line:
        try:
            reader.parse(line)
            line = logfile.readline()
            line_no += 1
        except NotImplementedError:
            raise NotImplementedError("Error in line %s: %s" % (line_no, line))

    html.finish()

    # Gather statistics and dump to log
    parser.log_statistics()


def main():
    if len(sys.argv) <= 1:
        print("Asciinema file missing. Specify session file to parse.")
        exit()

    elif len(sys.argv) <= 2:
        with open(sys.argv[1], mode="r", encoding="utf-8") as logfile:
            LOG.info("PlainOut:: Parsing file %s", sys.argv[1])
            parse(logfile)

    else:
        if not exists(dirname(sys.argv[2])):
            makedirs(dirname(sys.argv[2]))
        with open(sys.argv[2], mode='w', encoding="utf-8") as destfile:
            with open(sys.argv[1], mode="r", encoding="utf-8") as logfile:
                LOG.info("PlainOut:: Parsing file %s to %s", sys.argv[1], sys.argv[2])
                parse(logfile, destfile)
        # Copy over the asciinema files
        acpdir = dirname(sys.argv[2]) + "/" + ACP_DIR
        if not exists(acpdir):
            makedirs(acpdir)
        shutil.copy("acp/v2/asciinema-player.css", acpdir)
        shutil.copy("acp/v2/asciinema-player.js", acpdir)


if __name__ == '__main__':
    LOG_FORMAT = "%(levelname)s :%(module)s - %(message)s"
    logging.basicConfig(filename="parser.log",
                        level=logging.DEBUG,
                        format=LOG_FORMAT,
                        filemode='w')
    main()
