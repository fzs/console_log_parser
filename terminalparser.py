import logging
import re
import sys
from time import sleep
from vtparser import VT500Parser

LOG = logging.getLogger()



class TermLogParser(VT500Parser):
    """
    Parser that feeds terminal log data line by line to a VT500Parser and tries to find certain
    features in the log data. Such are the prompt, or when a vim editor is running.
    """

    # Parser state ids
    STATE_NORMAL = 0
    STATE_PROMPT_OSC = 1
    STATE_PROMPT_IMMINENT = 2
    STATE_PROMPT = 3

    # The regular expression to match prompt context
    RE_PROMPT_HEADER = "(?:\x1b\\[[0-9;]+m)?florian@Susie (?:\x1b\\[[0-9;]+m)?MINGW64(?:\x1b\\[[0-9;]+m)? (?:\x1b\\[[0-9;]+m)?(?P<cwd>[-.\\w/ ])+"

    class DefaultEventListener:
        def prompt_start(self):
            pass

        def prompt_end(self):
            pass

    def __init__(self):
        super().__init__()
        self.tlp_state = self.STATE_NORMAL
        self.tlp_event_listener = self.DefaultEventListener()
        self.osc_string = ''
        self.re_prompt_ctx = re.compile(self.RE_PROMPT_HEADER)

    def parse(self, line: bytes):
        """ Parse the input line code by code, while also trying to find patterns in the line """

        # Finding the prompt:
        #  A OSC string will try to set the window title. This is the marker that we have a prompt coming up.
        #  The next line will be the prompt context line and then in the next line we expect the '$'
        if self.tlp_state == self.STATE_PROMPT_OSC:
            # The OSC preceding prompts was seen. Check if the current line matches the prompt context
            str_line = line.decode()
            match = self.re_prompt_ctx.match(str_line)
            if match:
                if self.osc_string.endswith(match.group('cwd')):
                    self.tlp_state = self.STATE_PROMPT_IMMINENT
                else:
                    LOG.warning("We matched the prompt header, but the path doesn't match the OSC: %s", match.group('cwd'))

        elif self.tlp_state == self.STATE_PROMPT:
            self.emit(self.STATE_NORMAL)
            self.tlp_state = self.STATE_NORMAL

        for c in line:
            self.input(c)

            if self.tlp_state == self.STATE_PROMPT_IMMINENT and c == 0x24:  # check for '$'
                self.tlp_state = self.STATE_PROMPT
                self.emit(self.STATE_PROMPT)

    def emit(self, tlp_state):
        """ Emit an event that we have found some pattern in the parsed log """
        if tlp_state == self.STATE_PROMPT:
            self.tlp_event_listener.prompt_start()

        if tlp_state == self.STATE_NORMAL:
            if self.tlp_state == self.STATE_PROMPT:
                self.tlp_event_listener.prompt_end()

    # Override the osc methods so that we get a notification when to start checking for the prompt.
    # Actually this should be done with a OSC handler. But we want to keep the handler slot available
    # for an application to set with other output handlers. So we override methods instead and do the
    # checking "internally".
    # A better solution would probably be to be able to have a list of handlers instead of only one.
    # Or, so override a handler that may have been set. But that is probably not done safely in Python.
    def osc_start(self, code=None):
        super().osc_start(code)
        self.osc_string = ''

    def osc_put(self, code):
        super().osc_put(code)
        self.osc_string += chr(code)

    def osc_end(self, code=None):
        super().osc_end(code)
        # Check if this is the OSC that sets the window title. If so, transition to the state that a prompt is coming up
        if self.osc_string.startswith("0;"):
            self.tlp_state = self.STATE_PROMPT_OSC







def parse(logfile):
    """Read the input file line by line """
    parser = TermLogParser()
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
        LOG.info("Parsing file %s", sys.argv[1])
        parse(logfile)


if __name__ == '__main__':
    LOG_FORMAT = "%(levelname)s :%(module)s - %(message)s"
    logging.basicConfig(filename="parser.log",
                        level=logging.DEBUG,
                        format=LOG_FORMAT,
                        filemode='w')
    main()
