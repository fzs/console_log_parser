import logging
import sys
from terminalparser import TermLogParser
from vtparser import VT500Parser


LOG = logging.getLogger()


class HtmlDocumentCreator:
    """
    Take characters to print in `write` function and formatting
    information in `write_csi` function and write a formatted
    HTML file from it.
    """

    HTML_MAP = {
        '&': '&amp;',
        '>': '&gt;',
        '<': '&lt;',
        '"': '&quot;',
    }

    SCHEMES = {
        'Dracula': {
            'PC00': "#282a36", 'PC08': "#44475a",
            'PC01': "#ee3c3c", 'PC09': "#ff5555",
            'PC02': "#66de3d", 'PC10': "#50fa7b",
            'PC03': "#ffb86c", 'PC11': "#f1fa8c",
            'PC04': "#5443bc", 'PC12': "#6272a4",
            'PC05': "#bd93f9", 'PC13': "#ff79c6",
            'PC06': "#77d6fb", 'PC14': "#8be9fd",
            'PC07': "#f8f8f2", 'PC15': "#f8f8f2",
        },
        'MyDracula': {
            'PC00': "#21222c", 'PC08': "#6272a4",
            'PC01': "#ff5555", 'PC09': "#ff6e6e",
            'PC02': "#50fa7b", 'PC10': "#d6acff",
            'PC03': "#f1fa8c", 'PC11': "#ffffa5",
            'PC04': "#bd93f9", 'PC12': "#d6acff",
            'PC05': "#ff79c6", 'PC13': "#ff92df",
            'PC06': "#8be9fd", 'PC14': "#a4ffff",
            'PC07': "#f8f8f2", 'PC15': "#ffffff",
        },
        'TangoDark': {
            'PC00': "#000000", 'PC08': "#555753",
            'PC01': "#cc0000", 'PC09': "#ef2929",
            'PC02': "#4e9a06", 'PC10': "#8ae234",
            'PC03': "#c4a000", 'PC11': "#fce94f",
            'PC04': "#3465a4", 'PC12': "#729fcf",
            'PC05': "#ad7fa8", 'PC13': "#d6acff",
            'PC06': "#06989a", 'PC14': "#34e2e2",
            'PC07': "#d3d7cf", 'PC15': "#eeeeec",
        },
        'DarkBg': {
            True:  { 'F9': "PC07", 'B9': "PC00", 'bF9': "PC15" },
            False: { 'F9': "PC00", 'B9': "PC07", 'bF9': "PC08" },
        },
        'BoldAsBright': {
            True:  { 'fw': "normal" },
            False: { 'fw': "bold" },
        }
    }

    HTML_INTRO = """
<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
<title>%(title)s</title>
<style type="text/css">
h1 { text-align: center; color: #f0f5f5; }
h2 { text-align: center; color: #f0f5f5; }
pre { white-space: pre-wrap; }
.ef0,.f0 { color: %(PC00)s; } .eb0,.b0 { background-color: %(PC00)s; }
.ef1,.f1 { color: %(PC01)s; } .eb1,.b1 { background-color: %(PC01)s; }
.ef2,.f2 { color: %(PC02)s; } .eb2,.b2 { background-color: %(PC02)s; }
.ef3,.f3 { color: %(PC03)s; } .eb3,.b3 { background-color: %(PC03)s; }
.ef4,.f4 { color: %(PC04)s; } .eb4,.b4 { background-color: %(PC04)s; }
.ef5,.f5 { color: %(PC05)s; } .eb5,.b5 { background-color: %(PC05)s; }
.ef6,.f6 { color: %(PC06)s; } .eb6,.b6 { background-color: %(PC06)s; }
.ef7,.f7 { color: %(PC07)s; } .eb7,.b7 { background-color: %(PC07)s; }
.ef8, .f0 > .bold,.bold > .f0 { color: %(PC08)s; font-weight: %(fw)s; }
.ef9, .f1 > .bold,.bold > .f1 { color: %(PC09)s; font-weight: %(fw)s; }
.ef10,.f2 > .bold,.bold > .f2 { color: %(PC10)s; font-weight: %(fw)s; }
.ef11,.f3 > .bold,.bold > .f3 { color: %(PC11)s; font-weight: %(fw)s; }
.ef12,.f4 > .bold,.bold > .f4 { color: %(PC12)s; font-weight: %(fw)s; }
.ef13,.f5 > .bold,.bold > .f5 { color: %(PC13)s; font-weight: %(fw)s; }
.ef14,.f6 > .bold,.bold > .f6 { color: %(PC14)s; font-weight: %(fw)s; }
.ef15,.f7 > .bold,.bold > .f7 { color: %(PC15)s; font-weight: %(fw)s; }
.eb8  { background-color: %(PC08)s; }
.eb9  { background-color: %(PC09)s; }
.eb10 { background-color: %(PC10)s; }
.eb11 { background-color: %(PC11)s; }
.eb12 { background-color: %(PC12)s; }
.eb13 { background-color: %(PC13)s; }
.eb14 { background-color: %(PC14)s; }
.eb15 { background-color: %(PC15)s; }
.f9 { color: %(cf9)s; }
.b9 { background-color: %(cb9)s; }
.f9 > .bold,.bold > .f9, body.f9 > pre > .bold {
  /* Bold is heavy black on white, or bright white
     depending on the default background */
  color: %(bf9)s;
  font-weight: bold /*%(fw)s Just use bold. The bright white is not different enough*/;
}
.reverse {
  /* CSS does not support swapping fg and bg colours unfortunately,
     so just hardcode something that will look OK on all backgrounds. */
  color: %(PC00)s; background-color: %(PC07)s;
}
.underline { text-decoration: underline; }
.line-through { text-decoration: line-through; }
.blink { text-decoration: blink; }

.vim-session { color: #9696cc ; }

</style>
</head>

<body class="f9 b9">
<h1>%(title)s</h1>
<pre>
"""
    HTML_OUTRO = """
</pre>
</body>
</html>
"""

    def __init__(self, out_fh=sys.stdout, palette="MyDracula", dark_bg=True, title=None):
        self.fh = out_fh if out_fh is not None else sys.stdout
        self.palette = palette if palette is not None else 'MyDracula'
        self.dark_bg = dark_bg
        self.bold_as_bright = True
        self.title = title

        sdict = self.SCHEMES[self.palette].copy()
        sdict['fw'] = self.SCHEMES['BoldAsBright'][self.bold_as_bright]['fw']
        sdict['cf9'] = self.SCHEMES[self.palette][self.SCHEMES['DarkBg'][self.dark_bg]['F9']]
        sdict['cb9'] = self.SCHEMES[self.palette][self.SCHEMES['DarkBg'][self.dark_bg]['B9']]
        bf9 = self.SCHEMES['DarkBg'][self.dark_bg]['bF9'] if self.bold_as_bright else self.SCHEMES['DarkBg'][self.dark_bg]['F9']
        sdict['bf9'] = self.SCHEMES[self.palette][bf9]
        sdict['title'] = self.title

        self.html_intro = self.HTML_INTRO % sdict
        self.html_body_string = ""
        self.html_outro = self.HTML_OUTRO
        self.html_span_count = 0

        self.fh.write(self.html_intro)

    def write(self, char):
        if char in self.HTML_MAP:
            self.fh.write(self.HTML_MAP[char])
        else:
            self.fh.write(char)

    def convert_csi(self, _private, param, _intermediate, final):
        if final == 'm':
            span = ''
            if param == '' or param == '0' or param == '00':
                # close all spans
                span = "</span>" * self.html_span_count
                self.html_span_count = 0
            else:
                s_classes = []
                s_style = ''
                params = param.split(';')

                if params[0] == '38' or params[0] == '48':
                    # We handle the 38 and 48 controls only as a single control sequence,
                    # not when mixed with other parameters.
                    if len(params) != 3 and len(params) != 5 and len(params) != 6:
                        LOG.warning("Encountered SGR with incorrect parameter number, or mixed in with other paramters: %s",
                                    param)
                    else:
                        indicator = params[1]
                        if indicator == '5':  # Indexed Color
                            if params[0] == '38':
                                s_classes.append('ef' + params[2])
                            else:
                                s_classes.append('eb' + params[2])
                        else:  # RGB color
                            if params[0] == '38':
                                s_style = 'color:rgb(' + params[-3] + ',' + params[-2] + ',' + params[-1] + ')'
                            else:
                                s_style = 'background-color:rgb(' + params[-3] + ',' + params[-2] + ',' + params[-1] + ')'
                else:
                    for p in params:
                        if 30 <= int(p) <= 37:
                            s_classes.insert(0, "f" + p[-1])
                        elif 40 <= int(p) <= 47:
                            s_classes.insert(0, "b" + p[-1])
                        elif 90 <= int(p) <= 97:
                            s_classes.insert(0, "ef" + str(8 + int(p[-1])))
                        elif 100 <= int(p) <= 107:
                            s_classes.insert(0, "eb" + str(8 + int(p[-1])))
                        elif int(p) == 1:
                            s_classes.append('bold')
                        elif int(p) == 4:
                            s_classes.append('underline')
                        elif int(p) == 5:
                            s_classes.append('blink')
                        elif int(p) == 7:
                            s_classes.append('reverse')
                        elif p == '22':
                            LOG.warning("Ignoring reset code 22m. Output needs to be checked for consistency.")
                        else:
                            raise NotImplementedError("Implementation missing for CSI " + p + " m")
                for cls in s_classes:
                    span += '<span class="' + cls + '">'
                    self.html_span_count += 1
                if s_style:
                    span = '<span style="' + s_style + '">'
                    self.html_span_count += 1
            if span:
                self.fh.write(span)

    def new_cmd_block(self, count):
        """ Begin a new block of a prompt, command and command output. """
        if self.html_span_count:
            self.fh.write("</span>" * self.html_span_count)
            self.html_span_count = 0
        self.fh.write("\n</pre>\n<pre>\n")

    def vim_session(self):
        self.fh.write('<span class="vim-session">     [==-- Vim editor session --==]</span>\n')

    def finish(self):
        """ Finish output. Writing it out or closing a file or something. """
        self.fh.write(self.html_outro)
        if self.fh is not sys.stdout:
            self.fh.close()


class LineBuilder:
    """
    Build a text line from input with editing ANSI control characters and sequences.
    """
    def __init__(self):
        self.line = []
        self.pos = 0

    def print(self, code):
        """ Add a normal character """
        if self.pos >= len(self.line):
            self.line.insert(self.pos, code)
        else:
            self.line[self.pos] = code
        self.pos += 1

    def ctrl(self, code):
        """ Add a control character to be handled accordingly. """
        if code == 0x08:  # BS
            self.pos -= (1 if self.pos > 0 else 0)  # Go back one character
        if code == 0x09:  # TAB
            self.print(code)  # Treat as normal character, add via print
        elif code == 0x0D:  # CR
            self.pos = 0  # Back to start of line
        elif code == 0x0A:  # LF
            # This should terminate the command line. Add it so it gets printed.
            self.line.insert(len(self.line), code)
            self.pos += 1

    # Everything else is discarded, as we do not need it to build the command line

    def csi(self, private, param, interm, final, ignore_SGR=True):
        """ Add a control sequences to be handled accordingly.
        Might be editing the line or setting character attributes. """
        # Now it get's interesting.
        # Filter out the codes that effect the command line and discard all the rest.
        if final == '@' and interm == '':  # Insert blank characters
            times = 1 if param == '' else int(param)
            while times > 0:
                self.line.insert(self.pos, ord(' '))
                times -= 1
        elif final == 'C':  # Cursor forward
            times = 1 if param == '' else int(param)
            while times > 0:
                if self.pos >= len(self.line):  # Add spaces to the end of our line
                    self.line.append(ord(' '))
                self.pos += 1
                times -= 1
        elif final == 'D':  # Cursor backward
            p = 1 if param == '' else int(param)
            while self.pos >= 0 and p:
                self.pos -= 1
                p -= 1
        elif final == 'K':  # Erase in line
            if param == '' or param == '0':
                del self.line[self.pos:]
            else:
                # We need to handle this somehow should it appear
                raise NotImplementedError("Control sequence for Erase in Line not implemented: " + param + final)
        elif final == 'P':  # Delete Character
            p = 1 if param == '' else int(param)
            self.line[self.pos:self.pos+p] = []
        elif final == 'X':  # Erase Character
            times = 1 if param == '' else int(param)
            pos = self.pos
            while times > 0 and pos >= len(self.line):
                self.line[pos] = ord(' ')
                pos += 1
                times -= 1
        elif final == 'm':
            if ignore_SGR:
                LOG.info("Discard ignored SGR control sequence CSI %s%s %s %s", private, param, interm, final)
            else:
                self._insert_csi(private, param, interm, final)
        else:
            LOG.info("Discard unused control sequence CSI %s%s %s %s", private, param, interm, final)

    def _insert_csi(self, private, param, interm, final):
        if self.pos >= len(self.line):
            self.line.insert(self.pos, ('CSI', [private, param, interm, final]))
        else:
            self.line[self.pos] = ('CSI', [private, param, interm, final])
        self.pos += 1

    def reset(self):
        """ Clear line """
        self.line = []
        self.pos = 0


class VT2Html(VT500Parser.DefaultTerminalOutputHandler, VT500Parser.DefaultControlSequenceHandler,
              TermLogParser.DefaultEventListener):
    """
    Output class that writes the console session log to HTML format, recreating coloring, etc.

    Vim sessions are suppressed. In a later instance they could be added as asciinema inserts.
    """

    def __init__(self, document=None):
        self.command_line = LineBuilder()
        self.term_line = LineBuilder()

        self.in_prompt = False
        self.in_vim = False
        self.prompt_count = 0

        self.document = document if document else HtmlDocumentCreator()

    def print_cmd_line(self):
        # Start with the prompt and pause
        for code in self.command_line.line:
            self.document.write(chr(code))

    def print_term_line(self, line):
        for elem in line.line:
            if isinstance(elem, tuple):
                if elem[0] == 'CSI':
                    self.document.convert_csi(elem[1][0], elem[1][1], elem[1][2], elem[1][3])
            else:
                self.document.write(chr(elem))

    # Output handler methods
    def print(self, code):
        """The current code should be mapped to a glyph according to the character set mappings and shift states
         in effect, and that glyph should be displayed.

         Print normal characters to the HTML document."""
        if self.in_prompt:
            self.command_line.print(code)

        elif self.in_vim:
            # For now we ignore vim completely
            pass

        else:
            self.term_line.print(code)

    def execute(self, code):
        """The C0 or C1 control function should be executed, which may have any one of a variety of effects,
         including changing the cursor position, suspending or resuming communications or changing the
         shift states in effect. There are no parameters to this action.

         Controls would be a problem, since they have no place in the HTML output.
         When in the prompt, the controls are used to build up the command line.
         Otherwise only a LF goes through as relevant. TABs maybe?  And we may have to check for non-ASCII characters.
         Vim sessions are completely ignored."""
        if self.in_prompt:
            self.command_line.ctrl(code)

        elif self.in_vim:
            # For now we ignore vim completely
            pass

        elif code == 0x0A:  # EOL
            self.term_line.ctrl(code)
            self.print_term_line(self.term_line)
            self.term_line.reset()
        else:
            self.term_line.ctrl(code)

    def esc_dispatch(self, intermediate, final):
        """Ignore all escape sequences.
           Might have to change this when handling vim sessions."""
        pass

    def csi_dispatch(self, private, param, interm, final):
        """Control sequences for formatting, i.e. character attributes, are converted into HTML code.
           Control sequences that would trigger terminal responses are discarded.
           Control sequences for editing and movement are handled when building the command line.
           They would also need to be handled for vim sessions."""

        if final == "n":
            LOG.info("Discard Device Status Report CSI sequence %s%s", interm, final)
            return
        elif final == "c" and (param == '' or param == '0'):
            LOG.info("Discard Device Status Report CSI sequence %s%s", interm, final)
            return

        if self.in_prompt:
            self.command_line.csi(private, param, interm, final)
        elif self.in_vim:
            # For now we ignore vim completely
            pass
        else:
            self.term_line.csi(private, param, interm, final, False)

    # Event handler methods
    def prompt_start(self):
        self.prompt_count += 1
        self.document.new_cmd_block(self.prompt_count)

    def prompt_active(self):
        self.in_prompt = True
        self.command_line.reset()

    def prompt_end(self):
        self.print_cmd_line()
        self.in_prompt = False

    def vim_start(self):
        self.in_vim = True

    def vim_end(self):
        self.in_vim = False
        self.document.vim_session()


def parse(logfile, destfile=None, palette='MyDracula', title=None):
    """Read the input file byte by byte and output as HTML, either to a file or to stdout."""
    html = HtmlDocumentCreator(destfile, palette=palette, title=title)
    parser = TermLogParser()
    output_processor = VT2Html(html)
    parser.terminal_output_handler = output_processor
    parser.control_sequence_handler = output_processor
    parser.tlp_event_listener = output_processor

    line_no = 1
    line = logfile.readline()
    while line:
        try:
            parser.parse(line)
            line = logfile.readline()
            line_no += 1
        except NotImplementedError:
            raise NotImplementedError("Error in line %s: %s" % (line_no, line))

    html.finish()

    # Gather statistics and dump to log
    parser.log_statistics()


def main():
    if len(sys.argv) <= 1:
        print("Log file missing. Specify log file to parse.")
        exit()

    with open(sys.argv[1], 'rb') as logfile:
        LOG.info("PlainOut:: Parsing file %s", sys.argv[1])
        parse(logfile)


if __name__ == '__main__':
    LOG_FORMAT = "%(levelname)s :%(module)s - %(message)s"
    logging.basicConfig(filename="parser.log",
                        level=logging.DEBUG,
                        format=LOG_FORMAT,
                        filemode='w')
    main()
