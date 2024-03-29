import logging
import sys
import copy
import shutil
import json
import base64
import re
from os.path import dirname, exists, realpath
from os import makedirs

from terminal2html import VT2Html, HtmlDocumentCreator as VT2HtmlDocCreator
from terminalparser import TermLogParser
from vtparser import VT500Parser


LOG = logging.getLogger()


ACP_DIR = "js"
ACP_VER = 2


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
    .controls-help { white-space: pre-wrap; }
    pre.vimsession-dump { display: none }


    /* *** review mode: switch to display asciinema dump *** */
    input:checked~pre.vimsession-dump {  display: block;  }
    input.vimsession-dump { display: none }
    label.vimsession-dump { cursor:pointer; color: #13141a; }
    .review-frame-ts { color: cadetblue;   font-size: smaller; font-family: Orbitron, "PT Mono", Menlo, Bahnschrift, Consolas, sans-serif; }
    .review-cmd-hop  { color: navajowhite; font-size: smaller; font-family: Orbitron, "PT Mono", Menlo, Bahnschrift, Consolas, sans-serif; }
    .review-cmd-hop  { margin-bottom: 5ex; }
  </style>
"""

    STYLE_ASCIINEMA = """
  <link rel="stylesheet" type="text/css" href="{acpdir}/v{acpver}/asciinema-player.css" />
"""
    SCRIPT_ASCIINEMA = """
  <script src="{acpdir}/v{acpver}/asciinema-player.js"></script>
"""


    def __init__(self, out_fh=sys.stdout, palette="MyDracula", dark_bg=True, title=None, chapters={}, cmd_filter=[], hopto=None, review=False):
        super().HEAD_ELEMS['asciinema'] = [self.STYLE_DROPDOWN,
                                           self.STYLE_ASCIINEMA.format(acpdir=ACP_DIR, acpver=ACP_VER),
                                           self.SCRIPT_ASCIINEMA.format(acpdir=ACP_DIR, acpver=ACP_VER) ]
        super().__init__(out_fh, palette, dark_bg, title, chapters, cmd_filter, hopto)
        self.ddcount = 0
        self.vimsessions = {}
        self.review_mode = review
        self.frame_ts = 0.0
        if review:
            self.current_rev_hop = 0
            if not 'rev_hops' in self.hopto:
                self.hopto['rev_hops'] = [(float('inf'), float('inf'))]
            else:
                self.hopto['rev_hops'].append((float('inf'), float('inf')))


    def new_cmd_row(self, count):
        """ Begin a new command row, with command number and command, maybe a hop target link.  """
        self.end_cmd_row()

        LOG.debug("Beginning a new command row with frame ts at %f", self.frame_ts)

        if self.review_mode:
            self.add_review_hopto()

        self.add_hopto_link()

        if self.review_mode:
            # Add the frame number so we can match with the hop links during review
            self.fh.write('  <div class="review-frame-ts">{:f}</div>\n'.format(self.frame_ts))

        self.start_new_cmd_row()


    def add_review_hopto(self):
        if self.hopto['rev_hops'][self.current_rev_hop][0] <= self.frame_ts:
            LOG.debug("At ts %f detected previous jump from %f to %f", self.frame_ts, self.hopto['rev_hops'][self.current_rev_hop][0], self.hopto['rev_hops'][self.current_rev_hop][1])
            self.fh.write('\n  <div class="review-cmd-hop">\n')
            self.fh.write('    before TS {} detected jump to {}\n'
                          .format(self.frame_ts, self.hopto['rev_hops'][self.current_rev_hop][1]))
            self.fh.write('  </div>\n\n')
            self.current_rev_hop += 1



    def vim_session(self, vimrecording=None):
        if self.output_suppressed:
            return
        self.end_cmd_block()

        self.fh.write('      <details class="vimsession-dropdown">\n')
        self.fh.write('        <summary><span class="vim-session">  [==-- Vim editor session --==]</span></summary>\n')
        self.fh.write('        <div class="vimsession-player-wrapper">\n')

        session_id = str(self.ddcount) + '_' + str(self.cmd_number)
        if vimrecording is not None:
            if ACP_VER == 2:
                self.insert_vim_session_player_v2(vimrecording, session_id)
            else:
                self.insert_vim_session_player_v3(vimrecording, session_id)
            self.vimsessions[session_id] = vimrecording.to_string()
        else:
            self.fh.write('          <span class="vim-session">     [==-- THIS SHOULD BE A DROPDOWN ASCIINEMA RECORDING --==]</span>\n')

        self.fh.write('        </div>\n')
        self.fh.write('      </details>\n')
        self.ddcount += 1

        self.start_cmd_block()


    def insert_vim_session_player_v2(self, vimrecording, session_id):
        vimsession = vimrecording.to_string()
        acbase64 = base64.b64encode(vimsession.encode("utf-8"))
        self.fh.write('          <div>\n')
        self.fh.write('            <asciinema-player idle-time-limit="3" speed="1.75" poster="' + self.get_poster(vimrecording) + '" ')
        self.fh.write(                              'cols="{:d}" rows="{:d}" '.format(vimrecording.asciinfo['width'], vimrecording.asciinfo['height']))
        self.fh.write(                              'src="data:application/json;base64,' + acbase64.decode("ascii") + '" />\n')
        self.fh.write('          </div>\n')
        self.fh.write('          <div class="controls-help vim-session">\n')
        self.fh.write('  Controls: \n')
        self.fh.write('    space       - play / pause \n')
        self.fh.write('    < / >       - de- / increase playback speed\n')
        self.fh.write('    ← / →       - rewind / fast-forward 5 seconds\n')
        self.fh.write('    0, 1, ... 9 - jump to 0%, 10%, ... 90%\n')
        self.fh.write('          </div>\n')
        if self.review_mode:
            self.fh.write('          <input class="vimsession-dump" id="ddcheck'  + str(self.ddcount) + '" type="checkbox" name="asciinema"/>\n')
            self.fh.write('          <label class="vimsession-dump" for="ddcheck' + str(self.ddcount) + '">Show Vim editor session dump</label>\n')
            self.fh.write('          <pre class="vimsession-dump">\n')
            self.fh.write(vimsession + '\n')
            self.fh.write('          </pre>\n')

    def insert_vim_session_player_v3(self, vimrecording, session_id):
        vimsession = vimrecording.to_string()
        acbase64 = base64.b64encode(vimsession.encode("utf-8"))
        self.fh.write('          <div id="vimsess_' + session_id + '"></div>\n')
        self.fh.write('          <div class="controls-help vim-session">\n')
        self.fh.write('  Controls: \n')
        self.fh.write('    space  - play / pause\n')
        self.fh.write('    .      - step through a recording one frame at a time (when paused)\n')
        self.fh.write('    < / >  - decrease / increase playback speed\n')
        self.fh.write('    ← / →  - rewind 5 seconds / fast-forward 5 seconds\n')
        self.fh.write('    Shift + ← / Shift + → - rewind by 10% / fast-forward by 10%\n')
        self.fh.write('    0, 1, 2 ... 9         - jump to 0%, 10%, 20% ... 90%\n')
        self.fh.write('          </div>\n')
        if self.review_mode:
            self.fh.write('      <input class="vimsession-dump" id="ddcheck'  + str(self.ddcount) + '" type="checkbox" name="asciinema"/>\n')
            self.fh.write('      <label class="vimsession-dump" for="ddcheck' + str(self.ddcount) + '">Show Vim editor session dump</label>\n')
        self.fh.write('          <pre  class="vimsession-dump" id="vimsess_' + session_id + '_dump">[\n')
        self.fh.write(vimsession.replace('\n', ',\n') + '\n')
        self.fh.write(']         </pre>\n')
        self.fh.write('          <script>\n')
        self.fh.write("            AsciinemaPlayer.create('data:text/plain;base64," + acbase64.decode("ascii") + "', \n")
        self.fh.write("                                   document.getElementById('vimsess_" + session_id + "'), {\n")
        self.fh.write("                                      cols: {:d} , rows: {:d}, fit: false,\n"
                      .format(vimrecording.asciinfo['width'], vimrecording.asciinfo['height']))
        self.fh.write("                                      idleTimeLimit: 3, speed: 1.75, poster: '{:s}'\n"
                      .format(self.get_poster(vimrecording)))
        self.fh.write("                                   });\n")
        self.fh.write('          </script>\n')


    def get_poster(self, vimrecording):
        ts = vimrecording.get_end_time()
        if ts > 2.0:
            ts = ts - 1.0
        else:
            ts = ts - 0.4
        return "npt:" + str(ts)


    def dump_vim_sessions(self, path):
        if not exists(path):
            makedirs(path)
        for sessnum, session in self.vimsessions.items():
            with open(path + "/vim_session_" + sessnum + ".rec", mode='w', encoding="utf-8") as sessfile:
                sessfile.write(session)
                sessfile.close()


class VimRecording:
    """
    Recording a Vim session in a asciinema recording
    """
    def __init__(self, asciinfo):
        self.asciinfo = asciinfo
        self.last_ts = 0.0

    def start(self, start_ts, height = -1):
        self.last_ts = start_ts
        if (height >= 0):
            if height != self.asciinfo["height"]:
                LOG.debug("VimRecording:: Start vim recording at ts %s with height %s (overriding default %s)", start_ts, height, self.asciinfo["height"])
                asciinfo = copy.deepcopy(self.asciinfo)
                asciinfo["height"] = height
            else:
                LOG.debug("VimRecording:: Start vim recording at ts %s with height %s", start_ts, height)
                asciinfo = self.asciinfo
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

    def get_end_time(self):
        return self.frames[-1][0]

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
        self.document.frame_ts = frame[0]

        if self.in_vim:
            if self.capturing_vim:
                # Check if this frame includes the ending of the vim session.
                # If so, we end the capturing here without this and following frames,
                # so that our session replay doesn't close the vim secondary screen buffer.
                # Otherwise we include this frame in our session recording.
                if self.vim_ends_in_frame_line(termline):
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


    def vim_ends_in_frame(self, frame):
        frameline = frame[2].encode('utf-8')
        return self.vim_ends_in_frame_line(frameline)

    def vim_ends_in_frame_line(self, frameline):
        match = self.re_vim_end_1.search(frameline, re.MULTILINE)
        if not match:
            match = self.re_vim_end_2.search(frameline, re.MULTILINE)
        return False if not match else True


    # Event handler methods
    def vim_start(self, ev_props):
        self.in_vim = True
        # Start a new vim session as asciinema recording
        self.capturing_vim = True
        # This needs to be timed relative to the timestamp from the frame that started the vim session
        if ev_props is not None and "height" in ev_props:
            height = int(ev_props["height"])
        else:
            height = -1

        self.vimrecording.start(self.framebuffer[0][0], height)
        # Check if the last frame includes the vim ending, since it also just triggered the session start
        if self.vim_ends_in_frame(self.framebuffer[-1]):
            self.framebuffer.pop()
            self.capturing_vim = False
        self.vimrecording.addall(self.framebuffer)


    def vim_end(self):
        self.in_vim = False
        self.capturing_vim = False  # Just in case
        self.document.vim_session(self.vimrecording)



def parse(logfile, destfile=None, palette='MyDracula', title=None, chapters={}, cmd_filter=[], hopto=None, review=False):
    """Read the input file byte by byte and output as HTML, either to a file or to stdout."""

    line = logfile.readline()
    asciinfo = json.loads(line)
    if not asciinfo.get('version') == 2:
        print("Asciinema file is not a version 2 recording. Cannot parse this file.")
        exit()

    html = HtmlDocumentCreator(destfile, palette=palette, title=title, chapters=chapters, cmd_filter=cmd_filter, hopto=hopto, review=review)
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

    return html


def copy_asciinema_files(destdir):
    basedir = dirname(realpath(__file__))
    acp_srcdir = basedir + "/acp/v" + str(ACP_VER)

    # Copy over the asciinema files
    acp_dstdir = destdir + "/" + ACP_DIR + "/v" + str(ACP_VER)
    LOG.info("Copying player files from '%s' to '%s'", acp_srcdir, acp_dstdir)
    if not exists(acp_dstdir):
        makedirs(acp_dstdir)
    if ACP_VER == 2:
        shutil.copy(acp_srcdir + "/asciinema-player.css", acp_dstdir)
        shutil.copy(acp_srcdir + "/asciinema-player.js", acp_dstdir)
    else:
        shutil.copy(acp_srcdir + "/asciinema-player.css", acp_dstdir)
        shutil.copy(acp_srcdir + "/asciinema-player.min.js", acp_dstdir + "/asciinema-player.js")


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
                html = parse(logfile, destfile)

        copy_asciinema_files(dirname(sys.argv[2]))

        html.dump_vim_sessions(dirname(sys.argv[2]) + "/vs")



if __name__ == '__main__':
    LOG_FORMAT = "%(levelname)s :%(module)s - %(message)s"
    logging.basicConfig(filename="parser.log",
                        level=logging.DEBUG,
                        format=LOG_FORMAT,
                        filemode='w')
    logging.getLogger('vtparser').setLevel(logging.WARNING)
    main()
