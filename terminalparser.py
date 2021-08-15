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
    STATE_VIM_START = 4
    STATE_VIM_SESSION_ONELINE = 5
    STATE_VIM_ENDING = 7

    # The regular expression to match prompt context
    RE_PROMPT_HEADER = b"(?:\x1b\\[[0-9;]+m)?florian@Susie (?:\x1b\\[[0-9;]+m)?MINGW64(?:\x1b\\[[0-9;]+m)? (?:\x1b\\[[0-9;]+m)?(?P<cwd>[-.\\w/ ~]+)"
    RE_VIM_START = b".*\x1b\\[[0-9];(?P<height>[0-9]+)r(?:.*\x1b\\[[0-9]+;[0-9]+H\"(?P<file>[^\"]+)\")?.*\x1b\\[2;1H\xe2\x96\xbd\x1b\\[6n\x1b\\[2;1H  "
    RE_VIM_END = b".*\x1b\\[\\?1l\x1b>"

    class DefaultEventListener:
        def prompt_start(self):
            pass

        def prompt_end(self):
            pass

        def vim_start(self):
            pass

        def vim_end(self):
            pass

    def __init__(self):
        super().__init__()
        self.tlp_state = self.STATE_NORMAL
        self.tlp_event_listener = self.DefaultEventListener()
        self.osc_string = ''
        self.re_prompt_ctx = re.compile(self.RE_PROMPT_HEADER)
        self.re_vim_start = re.compile(self.RE_VIM_START)
        self.re_vim_end = re.compile(self.RE_VIM_END)

    def parse(self, line: bytes):
        """ Parse the input line code by code, while also trying to find patterns in the line """

        # Finding the prompt:
        #  A OSC string will try to set the window title. This is the marker that we have a prompt coming up.
        #  The next line will be the prompt context line and then in the next line we expect the '$'
        if self.tlp_state == self.STATE_PROMPT_OSC:
            # The OSC preceding prompts was seen. Check if the current line matches the prompt context
            match = self.re_prompt_ctx.match(line)
            if match:
                cwd = match.group('cwd').decode()
                if self.osc_string.endswith(cwd) or cwd == '~':
                    self.tlp_state = self.STATE_PROMPT_IMMINENT
                    LOG.info("Entering TLP state PROMPT_IMMINENT")
                else:
                    LOG.warning("We matched the prompt header, but the path doesn't match the OSC: %s", cwd)

        elif self.tlp_state == self.STATE_PROMPT:
            self.emit(self.STATE_NORMAL)
            self.tlp_state = self.STATE_NORMAL
            LOG.info("Entering TLP state NORMAL")

        elif self.tlp_state == self.STATE_VIM_START:
            match = self.re_vim_end.match(line)
            if match:
                self.tlp_state = self.STATE_VIM_ENDING
                LOG.info("Entering TLP state VIM_ENDING")
                self.emit(self.STATE_VIM_ENDING)

        elif self.tlp_state == self.STATE_VIM_ENDING:
            self.emit(self.STATE_NORMAL)
            self.tlp_state = self.STATE_NORMAL
            LOG.info("Entering TLP state NORMAL")


        # Finding a vim session:
        #  Vim could be entered by 'vim' on the command line or also by various git actions.
        #  So instead going by what command was typed, we watch the data stream and try to find patterns
        #  that tell us that a vim session has started or ended, and ideally also when it goes into insert mode.
        #  But the latter may not be useful, because if we want to simulate typing, the scrolling would also be
        #  terribly slow.
        #
        #  When vim starts, it does not only keyboard switching (which would not be enough to detect vim only),
        #  but it also runs some tests to find out terminal behaviour. These should be unique enough that we can
        #  know that vim is starting.
        if 0x96 in line:
            match = self.re_vim_start.match(line)
            if match:
                LOG.info("=====>   vim is starting with file {} in height {}  <=======".format(match.group('file'), match.group('height')))
                # The vim session might be on only one single line, i.e. no 0x0A in the session
                match = self.re_vim_end.match(line[-70:])
                if match:
                    LOG.info("Entering TLP state VIM_SESSION_ONELINE")
                    self.tlp_state = self.STATE_VIM_SESSION_ONELINE
                else:
                    self.tlp_state = self.STATE_VIM_START
                    LOG.info("Entering TLP state VIM_START")
                self.emit(self.STATE_VIM_START)
            else:
                LOG.warning("A vim session start was suspected but the regex didn't match")

        for c in line:
            if self.tlp_state == self.STATE_PROMPT_IMMINENT and c == 0x24:  # check for '$'
                self.tlp_state = self.STATE_PROMPT
                LOG.info("Entering TLP state PROMPT")
                self.emit(self.STATE_PROMPT)

            self.input(c)

    def emit(self, tlp_state):
        """ Emit an event that we have found some pattern in the parsed log """
        if tlp_state == self.STATE_PROMPT:
            self.tlp_event_listener.prompt_start()

        if tlp_state == self.STATE_VIM_START:
            self.tlp_event_listener.vim_start()

        if tlp_state == self.STATE_VIM_ENDING:
            LOG.info("Event STATE_VIM_ENDING has currently no mapped event.")

        if tlp_state == self.STATE_NORMAL:
            if self.tlp_state == self.STATE_PROMPT:
                self.tlp_event_listener.prompt_end()
            elif self.tlp_state == self.STATE_VIM_START or self.tlp_state == self.STATE_VIM_SESSION_ONELINE:
                self.tlp_event_listener.vim_end()
            elif self.tlp_state == self.STATE_VIM_ENDING:
                self.tlp_event_listener.vim_end()


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
            if self.tlp_state == self.STATE_VIM_START or self.tlp_state == self.STATE_VIM_SESSION_ONELINE\
                    or self.tlp_state == self.STATE_VIM_ENDING:
                self.emit(self.STATE_NORMAL)
            self.tlp_state = self.STATE_PROMPT_OSC
            LOG.info("Entering TLP state PROMPT_OSC")








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
