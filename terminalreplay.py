import logging
import sys
from time import sleep
from terminalparser import TermLogParser
from vtparser import VT500Parser


LOG = logging.getLogger()


class VT2Output(VT500Parser.DefaultTerminalOutputHandler, VT500Parser.DefaultControlSequenceHandler):
    """
    Output class that writes the console session log to stdout, recreating coloring, etc.
    It suppresses vim's terminal query control functions that would trigger terminal responses.
    The output of commands entered at the prompt are printed out simulating typing with delays.
    """
    in_prompt = False
    speed = 0.5

    def print(self, code):
        """The current code should be mapped to a glyph according to the character set mappings and shift states
         in effect, and that glyph should be displayed.
         We print normal output to stdout. Only delayed when in the prompt."""
        sys.stdout.write(chr(code))
        if VT2Output.in_prompt:
            sleep(0.2 * VT2Output.speed)
            sys.stdout.flush()

    def execute(self, code):
        """The C0 or C1 control function should be executed, which may have any one of a variety of effects,
         including changing the cursor position, suspending or resuming communications or changing the
         shift states in effect. There are no parameters to this action.
         We print control directly to stdout. Except when in the prompt of when ending the prompt. Then
         a delay is added."""
        if VT2Output.in_prompt and code == 0x0d:
            sleep(0.8)

        sys.stdout.write(chr(code))

        if VT2Output.in_prompt:
            sleep(0.1 * VT2Output.speed)
            sys.stdout.flush()

    def esc_dispatch(self, intermediate, final):
        """Execute all control sequences"""
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
        sys.stdout.write(ctrlstring)


class EventListener(TermLogParser.DefaultEventListener):
    output_handler = None

    def prompt_start(self):
        sys.stdout.flush()
        sleep(0.8)
        VT2Output.in_prompt = True

    def prompt_end(self):
        sys.stdout.flush()
        VT2Output.in_prompt = False


def parse(logfile):
    """Read the input file byte by byte and output as plain text to stdout"""
    parser = TermLogParser()
    parser.terminal_output_handler = VT2Output()
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
