import logging
import sys
import time
from time import sleep
from terminalparser import TermLogParser
from vtparser import VT500Parser


LOG = logging.getLogger()


class VT2PlainOutput(VT500Parser.DefaultTerminalOutputHandler, VT500Parser.DefaultControlSequenceHandler):
    """
    Parser class that writes the console log text as plain output, i.e. without any
    formatting, to stdout.
    """
    in_prompt = False

    def print(self, code):
        """The current code should be mapped to a glyph according to the character set mappings and shift states
         in effect, and that glyph should be displayed."""
        sys.stdout.write(chr(code))
        if VT2PlainOutput.in_prompt:
            time.sleep(0.2)
            sys.stdout.flush()

    def execute(self, code):
        """The C0 or C1 control function should be executed, which may have any one of a variety of effects,
         including changing the cursor position, suspending or resuming communications or changing the
         shift states in effect. There are no parameters to this action."""
        if VT2PlainOutput.in_prompt and code == 0x0d:
            time.sleep(0.8)

        sys.stdout.write(chr(code))

        if VT2PlainOutput.in_prompt:
            time.sleep(0.1)
            sys.stdout.flush()

    def csi_dispatch(self, private, param, interm, final):
        if final in "K":
            LOG.info("Send control function %s to output", final)
            ctrlstring = f"\x1b[{private}{param}{interm}{final}"
            LOG.info("Full control function: %s", ctrlstring)
            sys.stdout.write(ctrlstring)


class EventListener(TermLogParser.DefaultEventListener):
    output_handler = None

    def prompt_active(self):
        sys.stdout.flush()
        time.sleep(0.8)
        VT2PlainOutput.in_prompt = True

    def prompt_end(self):
        sys.stdout.flush()
        VT2PlainOutput.in_prompt = False


def parse(logfile):
    """Read the input file byte by byte and output as plain text to stdout"""
    parser = TermLogParser()
    parser.terminal_output_handler = VT2PlainOutput()
    parser.control_sequence_handler = parser.terminal_output_handler
    parser.tlp_event_listener = EventListener()

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
