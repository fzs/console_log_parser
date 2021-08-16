import logging
import sys
from time import sleep
from terminalparser import TermLogParser
from vtparser import VT500Parser


LOG = logging.getLogger()


class VT2Output(VT500Parser.DefaultTerminalOutputHandler, VT500Parser.DefaultControlSequenceHandler,
                TermLogParser.DefaultEventListener):
    """
    Output class that writes the console session log to stdout, recreating coloring, etc.
    It suppresses vim's terminal query control functions that would trigger terminal responses.
    The output of commands entered at the prompt are printed out simulating typing with delays.
    """

    def __init__(self):
        self.speed = 3
        self.cleanup_cmdline = True
        self.print_vim = False

        self.command_line = []
        self.cmd_line_pos = 0
        self.in_prompt = False
        self.in_vim = False


    def print(self, code):
        """The current code should be mapped to a glyph according to the character set mappings and shift states
         in effect, and that glyph should be displayed.
         We print normal output to stdout. Only delayed when in the prompt."""
        if self.in_prompt:
            if self.cleanup_cmdline:
                self.build_cmd_line_print(code)
            else:
                sleep(0.2 * (1.0/self.speed))
                sys.stdout.write(chr(code))
                sys.stdout.flush()

        elif self.in_vim:
            if self.print_vim:
                if 0x21 <= code <= 0x7d:
                    sleep(0.2 * (0.5 / self.speed))
                sys.stdout.write(chr(code))
                sys.stdout.flush()

        else:
            sys.stdout.write(chr(code))

    def execute(self, code):
        """The C0 or C1 control function should be executed, which may have any one of a variety of effects,
         including changing the cursor position, suspending or resuming communications or changing the
         shift states in effect. There are no parameters to this action.
         We print control directly to stdout. Except when in the prompt of when ending the prompt. Then
         a delay is added."""
        if self.in_prompt:
            if self.cleanup_cmdline:
                self.build_cmd_line_ctrl(code)
            else:
                if code == 0x0d: # Wait at CR, because this might be the end of the command input
                    sleep(0.8)
                sys.stdout.write(chr(code))
                sleep(0.1 * (1.0/self.speed))
                sys.stdout.flush()
        elif self.in_vim and not self.print_vim:
            pass
        else:
            sys.stdout.write(chr(code))

    def esc_dispatch(self, intermediate, final):
        """Execute all control sequences"""
        if self.in_vim and not self.print_vim:
            return
        ctrlstring = f"\x1b{intermediate}{final}"
        LOG.info("Emit to stdout full ESC control function: %s", ctrlstring)
        sys.stdout.write(ctrlstring)

    def csi_dispatch(self, private, param, interm, final):
        """Only certain control sequences are caught an discarded. Namely the ones that would trigger
        terminal responses. These are used by vim, but since vim is not running, no one is listening to
        the responses."""
        if final == "n":
            LOG.info("Discard Device Status Report CSI sequence %s%s", interm, final)
            return
        elif final == "c" and (param == '' or param == '0'):
            LOG.info("Discard Device Status Report CSI sequence %s%s", interm, final)
            return

        ctrlstring = f"\x1b[{private}{param}{interm}{final}"
        LOG.info("Emit to stdout full CSI control function: %s", ctrlstring)

        if self.in_prompt:
            if self.cleanup_cmdline:
                self.build_cmd_line_csi(private, param, interm, final)
            else:
                sleep(0.1 * (1.0/self.speed))
                sys.stdout.write(ctrlstring)
                sys.stdout.flush()
        elif self.in_vim and not self.print_vim:
            pass
        else:
            sys.stdout.write(ctrlstring)


    def build_cmd_line_print(self, code):
        if self.cmd_line_pos >= len(self.command_line):
            self.command_line.insert(self.cmd_line_pos, code)
        else:
            self.command_line[self.cmd_line_pos] = code
        self.cmd_line_pos += 1

    def build_cmd_line_ctrl(self, code):
        if code == 0x08:  # BS
            self.cmd_line_pos -= (1 if self.cmd_line_pos > 0 else 0)  # Go back one character
        elif code == 0x0D:  # CR
            self.cmd_line_pos = 0  # Back to start of line
        elif code == 0x0A:  # LF
            # This should terminate the command line. Add it so it gets printed.
            self.command_line.insert(len(self.command_line), code)
            self.cmd_line_pos +=1

        # Everything else is discarded, as we do not need it to build the command line

    def build_cmd_line_csi(self, private, param, interm, final):
        # Now it get's interesting.
        # Filter out the codes that effect the command line and discard all the rest.
        if final == '@' and interm == '':  # Insert blank characters
            self.command_line.insert(self.cmd_line_pos, ' ' if param == '' else ' ' * int(param))
        elif final == 'C':  # Cursor forward
            self.cmd_line_pos += 1 if param == '' else int(param)
        elif final == 'D':  # Cursor backward
            p = 1 if param == '' else int(param)
            while self.cmd_line_pos >= 0 and p:
                self.cmd_line_pos -= 1
                p -= 1
        elif final == 'K':  # Erase in line
            if param == '' or param == '0':
                del self.command_line[self.cmd_line_pos:]
            else:
                # We need to handle this somehow should it appear
                raise NotImplementedError("Control sequence for Erase in Line not implemented: " + param + final)
        elif final == 'P':  # Delete Character
            p = 1 if param == '' else int(param)
            self.command_line[self.cmd_line_pos:self.cmd_line_pos+p] = []

    def print_cmd_line(self):
        # Start with the prompt and pause
        i = self.command_line.index(ord(' '))
        for code in self.command_line[:i+1]:
            sys.stdout.write(chr(code))
        sys.stdout.flush()
        sleep(0.8)

        for code in self.command_line[i+1:]:
            if code == 0x0A:
                # Pause before we end the line
                sleep(0.8)
            sys.stdout.write(chr(code))
            sleep(0.2 * (1.0/self.speed))
            sys.stdout.flush()

    def prompt_active(self):
        if not self.cleanup_cmdline:
            sys.stdout.flush()
            sleep(0.8)
        self.in_prompt = True
        self.command_line = []
        self.cmd_line_pos = 0

    def prompt_end(self):
        if self.cleanup_cmdline:
            self.print_cmd_line()
        sys.stdout.flush()
        self.in_prompt = False

    def vim_start(self):
        self.in_vim = True

    def vim_end(self):
        self.in_vim = False
        sleep(1)


def parse(logfile):
    """Read the input file byte by byte and output as plain text to stdout"""
    parser = TermLogParser()
    output_processor = VT2Output()
    parser.terminal_output_handler = output_processor
    parser.control_sequence_handler = output_processor
    parser.tlp_event_listener = output_processor

    line = logfile.readline()
    while line:
        parser.parse(line)
        line = logfile.readline()

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
