import logging
import re
import html
import sys
import json
from os.path import dirname, exists
from os import makedirs

from terminal2html import VT2Html, HtmlDocumentCreator as VT2HtmlDocCreator
from terminalparser import TermLogParser
from vtparser import VT500Parser


LOG = logging.getLogger()




class HtmlDocumentCreator(VT2HtmlDocCreator):
    """
    HTML document creator that can add asciinema recordings for vim sessions
    """

    STYLE_DROPDOWN = """
  <style type="text/css">
    /* *** Dropdown for asciinema sessions *** */
    
    input, div.dropdown {  display: none;  }
    label { position: relative; display: block; cursor:pointer; }
    input:checked~div.dropdown {  display: block;  }
    input + label::before  { content: "   \\25B6   ";  }
    input:checked + label::before  { content: "   \\25BC   ";  }
    
    .vim-session { font-family: monospace; }
    .vimsession-wrapper { position: relative; top: -6ex; margin-bottom: -6ex }
  </style>
"""

    def __init__(self, out_fh=sys.stdout, palette="MyDracula", dark_bg=True, title=None, chapters={}, cmd_filter=[], hopto=None):
        super().HEAD_ELEMS.extend([self.STYLE_DROPDOWN])
        super().__init__(out_fh, palette, dark_bg, title, chapters, cmd_filter, hopto)
        self.ddcount = 0


    def vim_session(self):
        if self.output_suppressed:
            return
        self.end_cmd_block()

        self.fh.write('      <div class="vimsession-wrapper">\n')
        self.fh.write('        <input id="ddcheck' + str(self.ddcount) + '" type="checkbox" name="asciinema"/>\n')
        self.fh.write('        <label for="ddcheck' + str(self.ddcount) + '"><span class="vim-session">  [==-- Vim editor session --==]</span></label>\n')
        self.fh.write('        <div class="dropdown">\n')
        self.fh.write('          <span class="vim-session">     [==-- THIS SHOULD BE A DROPDOWN ASCIINEMA RECORDING --==]</span>\n')
        self.fh.write('        </div>\n')
        self.fh.write('      </div>\n')
        self.ddcount += 1

        self.start_cmd_block()


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

    def parse(self, line):
        frame = json.loads(line)
        for c in frame[2].encode('utf-8'):
            self.byteline.append(c)
            if c == 0x0A:
                self.parser.parse(self.byteline)
                self.byteline.clear()


    # def vim_start(self):
    #     self.in_vim = True
    #
    # def vim_end(self):
    #     self.in_vim = False
    #     self.document.vim_session()



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


if __name__ == '__main__':
    LOG_FORMAT = "%(levelname)s :%(module)s - %(message)s"
    logging.basicConfig(filename="parser.log",
                        level=logging.DEBUG,
                        format=LOG_FORMAT,
                        filemode='w')
    main()
