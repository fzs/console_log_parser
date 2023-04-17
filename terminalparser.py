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
    RE_PROMPT_HEADER = b"(?:\x1b\\[[0-9;]+m)?[a-z.]+@[-a-zA-Z0-9]+ (?:\x1b\\[[0-9;]+m)?MINGW64(?:\x1b\\[[0-9;]+m)? (?:\x1b\\[[0-9;]+m)?(?P<cwd>(~?[-.\\w/ ]+|~))"
    RE_PROMPT = b"(?:\x1b\\[[0-9;]+m)?[a-z.]+(?:(?:\x1b\\[[0-9;]+m)?@(?:\x1b\\[[0-9;]+m)?[-a-zA-Z0-9]+)?(?:\x1b\\[[0-9;]+m)?(?::| )(?:\x1b\\[[0-9;]+m)?(?P<cwd>(~?[-.\\w/ ]+|~))(?:\x1b\\[[0-9;]+m)?(?:(?:\x1b\\[[0-9;]+m) \\({1,2}[-.\\w/|! ]+\\){1,2} (?:\x1b\\[[0-9;]+m))?(?:\x1b\\[[0-9;]+m)?\\$(?:\x1b\\[00m)? "
    RE_PROMPT_LINESTART = b"^" + RE_PROMPT
    RE_PROMPT_INLINE = b"(?:\x1b\\[\\?1049l\x1b\\[23;0;0t)?" + RE_PROMPT   # With a possible end-of-man-page-session prefixed
    RE_PROMPT_POSTVIM = b"(?:\r\x1b\\[K)?" + RE_PROMPT                     # With a possible clear-line prefixed
    VIM_START = b"hint: Waiting for your editor to close the file... "
    RE_VIM_START_0 = b"(?:\x1b\\[\\?2004l\r)?" + VIM_START
    RE_VIM_START_1 = b".*(?P<t2200>\x1b\\[22;0;0t)(?:.*\x1b\\[[0-9];(?P<height>[0-9]+)r)?.*(?:\x1b\\[22;2t\x1b\\[22;1t)"
    RE_VIM_START_2 = b".*\x1b\\[[0-9];(?P<height>[0-9]+)r(?:.*\x1b\\[[0-9]+;[0-9]+H\"(?P<file>[^\"]+)\")?.*\x1b\\[2;1H\xe2\x96\xbd\x1b\\[6n\x1b\\[2;1H  "
    RE_VIM_END_1 = b".*\x1b\\[23;0;0t"
    RE_VIM_END_2 = b".*\x1b\\[\\?1l\x1b>"

    class DefaultEventListener:
        def prompt_start(self):
            pass

        def prompt_active(self):
            pass

        def prompt_end(self):
            pass

        def vim_start(self, ev_props):
            pass

        def vim_end(self):
            pass

    class AppModeStateMachine:
        """ A state machine to detect when application mode is entered and exited. """
        def __init__(self):
            self.app_mode_active = False
            self.ckm_set_pos = -1     # Position a Set Cursor Key Mode (application) was seen
            self.ckm_reset_pos = -1   # Position a Reset Cursor Key Mode (cursor) was seen

        def input(self, code, pos):
            """ Consume input code and transition states if applicable. If a state transition results
            from the input code, a 'enter' or 'exit' event is returned. """
            if code == 'DECCKM-S':
                self.ckm_set_pos = pos
            elif code == 'DECKPAM':
                if self.ckm_set_pos == pos - 2 and not self.app_mode_active:
                    self.app_mode_active = True
                    return 'enter'
            elif code == 'DECCKM-R':
                self.ckm_reset_pos = pos
            elif code == 'DECKPNM':
                if self.ckm_reset_pos == pos - 2 and self.app_mode_active:
                    self.app_mode_active = False
                    return 'exit'
            return ''


    def __init__(self):
        super().__init__()
        self.tlp_state = self.STATE_NORMAL
        self.tlp_event_listener = self.DefaultEventListener()
        self.app_mode = self.AppModeStateMachine()
        self.osc_string = ''
        self.line = None
        self.line_pos = 0
        self.re_prompt = re.compile(self.RE_PROMPT)
        self.re_prompt_ctx = re.compile(self.RE_PROMPT_HEADER)
        self.re_prompt_linestart = re.compile(self.RE_PROMPT_LINESTART)
        self.re_prompt_inline = re.compile(self.RE_PROMPT_INLINE)
        self.re_prompt_post_vim = re.compile(self.RE_PROMPT_POSTVIM)
        self.re_vim_start_0 = re.compile(self.RE_VIM_START_0)
        self.re_vim_start_1 = re.compile(self.RE_VIM_START_1)
        self.re_vim_start_2 = re.compile(self.RE_VIM_START_2)
        self.re_vim_end_1 = re.compile(self.RE_VIM_END_1)
        self.re_vim_end_2 = re.compile(self.RE_VIM_END_2)
        self.vim_2200_seen = False
        self.next_vim = -1

    def parse(self, line: bytes):
        """ Parse the input line code by code, while also trying to find patterns in the line """

        self.line = line

        # Finding the prompt:
        #  A OSC string will try to set the window title. This is the marker that we have a prompt coming up.
        #  The next line will be the prompt context line and then in the next line we expect the '$'
        if self.tlp_state == self.STATE_PROMPT_OSC:
            # The OSC preceding prompts was seen. Check if the current line matches the prompt context
            match = self.re_prompt_ctx.match(line)
            if match:
                cwd = match.group('cwd').decode()
                if self.osc_string.endswith(cwd[1:]) or cwd == '~':
                    self.tlp_state = self.STATE_PROMPT_IMMINENT
                    LOG.info("Entering TLP state PROMPT_IMMINENT")
                else:
                    LOG.warning("We matched the prompt header, but the path doesn't match the OSC: %s", cwd)

        elif self.tlp_state == self.STATE_PROMPT:
            self.emit(self.STATE_NORMAL)
            self.tlp_state = self.STATE_NORMAL
            LOG.info("Entering TLP state NORMAL")

        elif self.tlp_state == self.STATE_VIM_START:
            match1 = self.re_vim_end_1.match(line)
            match2 = self.re_vim_end_2.match(line)
            if match1 or match2:
                self.emit(self.STATE_VIM_ENDING)
                self.tlp_state = self.STATE_VIM_ENDING
                LOG.info("Entering TLP state VIM_ENDING")

        elif self.tlp_state == self.STATE_VIM_ENDING:
            self.emit(self.STATE_NORMAL)
            self.tlp_state = self.STATE_NORMAL
            LOG.info("Entering TLP state NORMAL")

        if self.tlp_state == self.STATE_NORMAL and self.re_prompt_linestart.match(line):
            self.emit(self.STATE_PROMPT_IMMINENT)
            self.tlp_state = self.STATE_PROMPT_IMMINENT
            LOG.info("Entering TLP state PROMPT_IMMINENT (prompt RE match)")


        # Finding a vim session:
        #  Vim could be entered by 'vim' on the command line or also by various git actions.
        #  So instead of going by what command was typed, we watch the data stream and try to find patterns
        #  that tell us that a vim session has started or ended, and ideally also when it goes into insert mode.
        #  But the latter may not be useful, because if we want to simulate typing, the scrolling would also be
        #  terribly slow.
        #
        #  When vim starts, it does not only keyboard switching (which would not be enough to detect vim only),
        #  but it also runs some tests to find out terminal behaviour. These should be unique enough that we can
        #  know that vim is starting.
        #  Turns out they are not, and instead we need to watch for xterm window label controls.
        if not (self.tlp_state == self.STATE_VIM_START or
                self.tlp_state == self.STATE_VIM_SESSION_ONELINE or
                self.tlp_state == self.STATE_VIM_ENDING):
            file = ''
            height = ''
            props = {}
            match2 = None

            match0 = self.re_vim_start_0.match(line)
            match1 = self.re_vim_start_1.match(line)
            if match1:
                self.vim_2200_seen = True
                if match1.group('height'):
                    props['height'] = match1.group('height')
                    height = " in height {}".format(match1.group('height'))
            else:
                self.vim_2200_seen = False
                match2 = self.re_vim_start_2.match(line)
                if match2:
                    if match2.group('height'):
                        props['height'] = match2.group('height')
                        height = " in height {}".format(match2.group('height'))
                    if match2.group('file'):
                        props['file'] = match2.group('file')
                        file = " with file {}".format(match2.group('file'))

            if match0 or match1 or match2:
                LOG.info("=====>   vim is starting {}{}  <=======".format(file, height))
                # The vim session might be on only one single line, i.e. no 0x0A in the session
                self.emit(self.STATE_VIM_START, props)
                match1 = self.re_vim_end_1.match(line[-70:])
                if match1:
                    LOG.info("Entering TLP state VIM_SESSION_ONELINE")
                    self.tlp_state = self.STATE_VIM_SESSION_ONELINE
                else:
                    match2 = self.re_vim_end_2.match(line[-70:])
                    if match2:
                        LOG.info("Entering TLP state VIM_SESSION_ONELINE")
                        self.tlp_state = self.STATE_VIM_SESSION_ONELINE
                    else:
                        self.tlp_state = self.STATE_VIM_START
                        LOG.info("Entering TLP state VIM_START")

            if match0 and not self.vim_2200_seen:
                LOG.warning("A vim session start was suspected but the 2200 regex didn't match")

        # Finally, feed the line character by character to the VT parser
        self.line_pos = 0
        for c in line:
            #  An OSC string will try to set the window title. This is the marker that we have a prompt coming up.
            #  Check if the prompt follows directly after in this line
            if self.tlp_state == self.STATE_PROMPT_OSC:
                # The OSC preceding prompts was seen. Check if the current line matches the prompt context
                match = self.re_prompt.match(line, self.line_pos)
                if match:
                    cwd = match.group('cwd').decode()
                    if self.osc_string.endswith(cwd[1:]) or cwd == '~':
                        self.tlp_state = self.STATE_PROMPT_IMMINENT
                        LOG.info("Entering TLP state PROMPT_IMMINENT")
                    else:
                        LOG.warning("We matched the prompt header, but the path doesn't match the OSC: %s", cwd)
            elif self.tlp_state == self.STATE_PROMPT_IMMINENT and c == 0x24:  # check for '$'
                self.emit(self.STATE_PROMPT)
                self.tlp_state = self.STATE_PROMPT
                LOG.info("Entering TLP state PROMPT")
            elif self.next_vim > 0 and self.line_pos == self.next_vim:
                # Another vim session is coming up in the line.
                # Check if we have reached it yet, and if so, go into Vim mode again.
                file = ''
                height = ''
                props = {}
                if line[self.line_pos:].startswith(self.VIM_START):  # Yup, here it comes
                    match1 = self.re_vim_start_1.match(line[self.line_pos:])
                    if match1:
                        self.vim_2200_seen = True
                        if match1.group('height'):
                            props['height'] = match1.group('height')
                            height = " in height {}".format(match1.group('height'))
                    else:
                        self.vim_2200_seen = False
                        match2 = self.re_vim_start_2.match(line[self.line_pos:])
                        if match2:
                            if match2.group('height'):
                                props['height'] = match2.group('height')
                                height = " in height {}".format(match2.group('height'))
                            if match2.group('file'):
                                props['file'] = match2.group('file')
                                file = " with file {}".format(match2.group('file'))

                LOG.info("=====>   vim is starting again{}{}  <=======".format(file, height))
                # The vim session might be on only one single line, i.e. no 0x0A in the session
                self.emit(self.STATE_VIM_START, props)
                match1 = self.re_vim_end_1.match(line[-70:])
                if match1:
                    LOG.info("Entering TLP state VIM_SESSION_ONELINE")
                    self.tlp_state = self.STATE_VIM_SESSION_ONELINE
                else:
                    match2 = self.re_vim_end_2.match(line[-70:])
                    if match2:
                        LOG.info("Entering TLP state VIM_SESSION_ONELINE")
                        self.tlp_state = self.STATE_VIM_SESSION_ONELINE
                    else:
                        self.tlp_state = self.STATE_VIM_START
                        LOG.info("Entering TLP state VIM_START")

            self.input(c)
            self.line_pos += 1

    def emit(self, tlp_state, props=None):
        """ Emit an event that we have found some pattern in the parsed log """
        if tlp_state == self.STATE_PROMPT_OSC:
            if self.tlp_state == self.STATE_VIM_START or self.tlp_state == self.STATE_VIM_SESSION_ONELINE:
                self.tlp_event_listener.vim_end()
            elif self.tlp_state == self.STATE_VIM_ENDING:
                self.tlp_event_listener.vim_end()

            self.tlp_event_listener.prompt_start()

        if tlp_state == self.STATE_PROMPT_IMMINENT:
            self.tlp_event_listener.prompt_start()

        if tlp_state == self.STATE_PROMPT:
            self.tlp_event_listener.prompt_active()

        if tlp_state == self.STATE_VIM_START:
            self.tlp_event_listener.vim_start(props)

        if tlp_state == self.STATE_VIM_ENDING:
            LOG.info("Event STATE_VIM_ENDING has currently no mapped event.")

        if tlp_state == self.STATE_NORMAL:
            if self.tlp_state == self.STATE_PROMPT:
                self.tlp_event_listener.prompt_end()
            elif self.tlp_state == self.STATE_VIM_START or self.tlp_state == self.STATE_VIM_SESSION_ONELINE:
                self.tlp_event_listener.vim_end()
            elif self.tlp_state == self.STATE_VIM_ENDING:
                self.tlp_event_listener.vim_end()


    # Override the esc_dispatch method, so that we can react to a keyboard processing control function,
    # signaling the termination of application mode.
    # Actually this should be done with a ESC handler. But we want to keep the handler slot available
    # for an application to set with other output handlers. So we override methods instead and do the
    # checking "internally".
    # A better solution would probably be to be able to have a list of handlers instead of only one.
    # Or, to override a handler that may have been set. But that is probably not done safely in Python.
    def esc_dispatch(self, code):
        """The final character of an escape sequence has arrived. After the parent's method has run,
         check if this is a keypad mode function. In that case, an application mode could end and we should
         check for a prompt following in the line."""
        super().esc_dispatch(code)

        if self.final_char == '=':
            self.app_mode.input('DECKPAM', self.line_pos)
        elif self.final_char == '>':
            event = self.app_mode.input('DECKPNM', self.line_pos)
            if event == 'exit' and not (self.tlp_state == self.STATE_VIM_START or
                                        self.tlp_state == self.STATE_VIM_SESSION_ONELINE or
                                        self.tlp_state == self.STATE_VIM_ENDING):
                # Check if the next prompt follows directly after this application mode session
                match = self.re_prompt_inline.match(self.line, self.line_pos+1)
                if match:
                    self.emit(self.STATE_PROMPT_IMMINENT)
                    self.tlp_state = self.STATE_PROMPT_IMMINENT
                    LOG.info("Entering TLP state PROMPT_IMMINENT (prompt after application mode exit)")



    # Override the csi method, so that we can react to a window manipulation code, signaling
    # the termination of a vim session.
    # Actually this should be done with a OSC handler. But we want to keep the handler slot available
    # for an application to set with other output handlers. So we override methods instead and do the
    # checking "internally".
    # A better solution would probably be to be able to have a list of handlers instead of only one.
    # Or, to override a handler that may have been set. But that is probably not done safely in Python.
    def csi_dispatch(self, code):
        """A final character has arrived. After the parent's method has run, check if this is a CSI [ 23;0;0
         code and we are in a vim session. In that case the vim session ends here. Also feed mode codes to our
         mode state machine to detect end of application modes. Used for finding the prompt."""
        super().csi_dispatch(code)

        if self.final_char == 't' and self.parameter_string == '23;0;0'and self.private_flag == '' and self.intermediate_char == '':
            if self.vim_2200_seen and (self.tlp_state == self.STATE_VIM_START or
                                       self.tlp_state == self.STATE_VIM_SESSION_ONELINE or
                                       self.tlp_state == self.STATE_VIM_ENDING):
                self.emit(self.STATE_NORMAL)
                self.tlp_state = self.STATE_NORMAL
                LOG.info("Entering TLP state NORMAL, Vim ended with 23;0;0t")

                # Check if the next prompt follows directly after this vim session
                match = self.re_prompt_post_vim.match(self.line, self.line_pos+1)
                if match:
                    self.emit(self.STATE_PROMPT_IMMINENT)
                    self.tlp_state = self.STATE_PROMPT_IMMINENT
                    LOG.info("Entering TLP state PROMPT_IMMINENT (prompt after VIM_END_1 match)")

                # Special treatment for git command which may invoke multiple Vim sessions in one
                # output line, e.g. rebase -i
                # Check if there is another git induced Vim session in the remainder of the line.
                self.next_vim = self.line.find(self.VIM_START, self.line_pos)
                if self.next_vim > 0:
                    LOG.info("Another Vim session opening in same line at %d", self.next_vim)

        elif self.final_char == 'h' and self.parameter_string == '1'and self.private_flag == '?' and self.intermediate_char == '':
            self.app_mode.input('DECCKM-S', self.line_pos)
        elif self.final_char == 'l' and self.parameter_string == '1'and self.private_flag == '?' and self.intermediate_char == '':
            self.app_mode.input('DECCKM-R', self.line_pos)


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
            self.emit(self.STATE_PROMPT_OSC)
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
