import logging
import sys
from enum import Enum

LOG = logging.getLogger()


class States(Enum):
    """
    VT500 Parser state machine state ids.
    """
    GROUND = 'ground'
    ESCAPE = 'escape'
    ESCAPE_INTERMEDIATE = 'escape_intermediate'
    CSI_ENTRY = 'csi_entry'
    CSI_PARAM = 'csi_param'
    CSI_INTERMEDIATE = 'csi_intermediate'
    CSI_IGNORE = 'csi_ignore'
    DCS_ENTRY = 'dcs_entry'
    DCS_PARAM = 'dcs_param'
    DCS_INTERMEDIATE = 'dcs_intermediate'
    DCS_PASSTHROUGH = 'dcs_passthrough'
    DCS_IGNORE = 'dcs_ignore'
    OSC_STRING = 'osc_string'
    SOS_PM_APC_STRING = 'sos_pm_apc_string'


class Actions(Enum):
    """
    Vt500 parser state machine action ids.
    """
    IGNORE = 'ignore'
    PRINT = 'print'
    EXECUTE = 'execute'
    CLEAR = 'clear'
    COLLECT = 'collect'
    PARAM = 'param'
    ESC_DISPATCH = 'esc_dispatch'
    CSI_DISPATCH = 'csi_dispatch'
    HOOK = 'hook'
    PUT = 'put'
    UNHOOK = 'unhook'
    OSC_START = 'osc_start'
    OSC_PUT = 'osc_put'
    OSC_END = 'osc_end'


class State:
    """
    VT500Parser state machine state. It defines a mapping from an input code to a action and/or new state
    for each defined state of the state machine.
    """
    states = {}

    def __init__(self, state_id: States):
        # State id. In case someone wants to find out who we are.
        self.id = state_id
        # The event map defines for each input code a (action,state) tuple.
        # The tuple has an action if the event, i.e. input code, results
        # in an action, and it has a state if the event results in a
        # transition to a new state.
        # The keys of the map can be single codes, or tuples that define a
        # start and an end of a code range.
        #
        # The following defaults are always the same for all states.
        self.event_map = {
            # The CANcel and SUBstitute control codes are immediately executed
            # and always transition to 'ground'
            0x18: (Actions.EXECUTE, States.GROUND),
            0x1A: (Actions.EXECUTE, States.GROUND),
            # The ESCape code always starts a escape control, i.e. transition to 'escape'
            0x1B: (None, States.ESCAPE),
            # The following C1 controls get executed immediately and transition to 'ground'
            (0x80, 0x8F): (Actions.EXECUTE, States.GROUND),
            (0x91, 0x97): (Actions.EXECUTE, States.GROUND),
            0x99: (Actions.EXECUTE, States.GROUND),
            0x9A: (Actions.EXECUTE, States.GROUND),
            # The String Terminator control function always transitions to ground
            0x9C: (None, States.GROUND),
            # The SOS, PM and APC control functions are ignored and immediately transition
            # to 'sos_pm_apc_string' for that.
            0x98: (None, States.SOS_PM_APC_STRING),
            0x9E: (None, States.SOS_PM_APC_STRING),
            0x9F: (None, States.SOS_PM_APC_STRING),
            # The Device Control String control function always starts a new device control string
            0x90: (None, States.DCS_ENTRY),
            # The Control String Initiator control function always starts a new control string
            0x9B: (None, States.CSI_ENTRY),
            # The Operating System Command control function always starts a new OSC string
            0x9D: (None, States.OSC_STRING)
        }

    @classmethod
    def get(cls, state_id):
        if state_id in cls.states:
            return cls.states[state_id]
        else:
            state = State.generate_state(state_id)
            cls.states[state_id] = state
            return state

    def event(self, code):
        entry = None
        # All codes A0-ff (GR area) are treated identically
        # to codes 20-7F (GL area). So for these codes search the
        # mapping table  for the GL counterpart
        s_code = code
        if 0xA0 <= code <= 0xff:
            s_code = code - 0x80

        # First check if the code is in the map as a single key
        if s_code in self.event_map:
            entry = self.event_map[s_code]
        else:
            # Otherwise find a range in the keys in which the code does fit
            for key in self.event_map:
                if isinstance(key, tuple):
                    if key[0] <= s_code <= key[1]:
                        entry = self.event_map[key]

        if entry is not None:
            action, state_id = entry
            return (action, None if state_id is None else self.get(state_id))

        raise NotImplementedError("The input 0x{:02x} has no mapping defined.".format(code))
        #return None

    def entry(self):
        if 'entry' in self.event_map:
            return self.event_map['entry'][0]
        return None

    def exit(self):
        if 'exit' in self.event_map:
            return self.event_map['exit'][0]
        return None

    @staticmethod
    def generate_state(state_id):
        if state_id == States.GROUND:
            state = State(state_id)
            state.event_map[(0x00, 0x17)] = (Actions.EXECUTE, None)
            state.event_map[0x19]         = (Actions.EXECUTE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.EXECUTE, None)

            state.event_map[(0x20, 0x7F)] = (Actions.PRINT, None)
            return state

        if state_id == States.ESCAPE:
            state = State(state_id)
            state.event_map['entry'] = (Actions.CLEAR,)

            state.event_map[(0x00, 0x17)] = (Actions.EXECUTE, None)
            state.event_map[0x19]         = (Actions.EXECUTE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.EXECUTE, None)

            state.event_map[(0x20, 0x2F)] = (Actions.COLLECT, States.ESCAPE_INTERMEDIATE)

            state.event_map[(0x30, 0x4F)] = (Actions.ESC_DISPATCH, States.GROUND)
            state.event_map[(0x51, 0x57)] = (Actions.ESC_DISPATCH, States.GROUND)
            state.event_map[0x59]         = (Actions.ESC_DISPATCH, States.GROUND)
            state.event_map[0x5A]         = (Actions.ESC_DISPATCH, States.GROUND)
            state.event_map[0x5C]         = (Actions.ESC_DISPATCH, States.GROUND)
            state.event_map[(0x60, 0x7E)] = (Actions.ESC_DISPATCH, States.GROUND)

            state.event_map[0x58] = (None, States.SOS_PM_APC_STRING)
            state.event_map[0x5E] = (None, States.SOS_PM_APC_STRING)
            state.event_map[0x5F] = (None, States.SOS_PM_APC_STRING)

            state.event_map[0x50] = (None, States.DCS_ENTRY)
            state.event_map[0x5B] = (None, States.CSI_ENTRY)
            state.event_map[0x5D] = (None, States.OSC_STRING)

            state.event_map[0x7F] = (Actions.IGNORE, None)
            return state

        if state_id == States.ESCAPE_INTERMEDIATE:
            state = State(state_id)
            state.event_map[(0x00, 0x17)] = (Actions.EXECUTE, None)
            state.event_map[0x19]         = (Actions.EXECUTE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.EXECUTE, None)

            state.event_map[(0x20, 0x2F)] = (Actions.COLLECT, None)

            state.event_map[(0x30, 0x7E)] = (Actions.ESC_DISPATCH, States.GROUND)

            state.event_map[0x7F] = (Actions.IGNORE, None)
            return state

        if state_id == States.CSI_ENTRY:
            state = State(state_id)
            state.event_map['entry'] = (Actions.CLEAR,)

            state.event_map[(0x00, 0x17)] = (Actions.EXECUTE, None)
            state.event_map[0x19]         = (Actions.EXECUTE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.EXECUTE, None)

            state.event_map[(0x20, 0x2F)] = (Actions.COLLECT, States.CSI_INTERMEDIATE)

            state.event_map[(0x30, 0x39)] = (Actions.PARAM, States.CSI_PARAM)
            state.event_map[0x3B]         = (Actions.PARAM, States.CSI_PARAM)

            state.event_map[(0x3C, 0x3F)] = (Actions.COLLECT, States.CSI_PARAM)

            state.event_map[0x3A]         = (None, States.CSI_IGNORE)

            state.event_map[(0x40, 0x7E)] = (Actions.CSI_DISPATCH, States.GROUND)

            state.event_map[0x7F]         = (Actions.IGNORE, None)
            return state

        if state_id == States.CSI_PARAM:
            state = State(state_id)
            state.event_map[(0x00, 0x17)] = (Actions.EXECUTE, None)
            state.event_map[0x19]         = (Actions.EXECUTE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.EXECUTE, None)

            state.event_map[(0x20, 0x2F)] = (Actions.COLLECT, States.CSI_INTERMEDIATE)

            state.event_map[(0x30, 0x39)] = (Actions.PARAM, None)
            state.event_map[0x3B]         = (Actions.PARAM, None)

            state.event_map[0x3A]         = (None, States.CSI_IGNORE)
            state.event_map[(0x3C, 0x3F)] = (None, States.CSI_IGNORE)

            state.event_map[(0x40, 0x7E)] = (Actions.CSI_DISPATCH, States.GROUND)

            state.event_map[0x7F]         = (Actions.IGNORE, None)
            return state

        if state_id == States.CSI_INTERMEDIATE:
            state = State(state_id)
            state.event_map[(0x00, 0x17)] = (Actions.EXECUTE, None)
            state.event_map[0x19]         = (Actions.EXECUTE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.EXECUTE, None)

            state.event_map[(0x20, 0x2F)] = (Actions.COLLECT, None)

            state.event_map[(0x30, 0x3F)] = (None, States.CSI_IGNORE)

            state.event_map[(0x40, 0x7E)] = (Actions.CSI_DISPATCH, States.GROUND)

            state.event_map[0x7F]         = (Actions.IGNORE, None)
            return state

        if state_id == States.CSI_IGNORE:
            state = State(state_id)
            state.event_map[(0x00, 0x17)] = (Actions.EXECUTE, None)
            state.event_map[0x19]         = (Actions.EXECUTE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.EXECUTE, None)

            state.event_map[(0x20, 0x3F)] = (Actions.IGNORE, None)

            state.event_map[(0x40, 0x7E)] = (None, States.GROUND)

            state.event_map[0x7F]         = (Actions.IGNORE, None)
            return state

        if state_id == States.DCS_ENTRY:
            state = State(state_id)
            state.event_map['entry'] = (Actions.CLEAR,)

            state.event_map[(0x00, 0x17)] = (Actions.IGNORE, None)
            state.event_map[0x19]         = (Actions.IGNORE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.IGNORE, None)

            state.event_map[(0x20, 0x2F)] = (Actions.COLLECT, States.DCS_INTERMEDIATE)

            state.event_map[(0x30, 0x39)] = (Actions.PARAM, States.DCS_PARAM)
            state.event_map[0x3B]         = (Actions.PARAM, States.DCS_PARAM)

            state.event_map[(0x3C, 0x3F)] = (Actions.COLLECT, States.DCS_PARAM)

            state.event_map[0x3A]         = (None, States.DCS_IGNORE)

            state.event_map[(0x40, 0x7E)] = (None, States.DCS_PASSTHROUGH)

            state.event_map[0x7F]         = (Actions.IGNORE, None)
            return state

        if state_id == States.DCS_PARAM:
            state = State(state_id)
            state.event_map[(0x00, 0x17)] = (Actions.IGNORE, None)
            state.event_map[0x19]         = (Actions.IGNORE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.IGNORE, None)

            state.event_map[(0x20, 0x2F)] = (Actions.COLLECT, States.DCS_INTERMEDIATE)

            state.event_map[(0x30, 0x39)] = (Actions.PARAM, None)
            state.event_map[0x3B]         = (Actions.PARAM, None)

            state.event_map[0x3A]         = (None, States.DCS_IGNORE)
            state.event_map[(0x3C, 0x3F)] = (None, States.DCS_IGNORE)

            state.event_map[(0x40, 0x7E)] = (None, States.DCS_PASSTHROUGH)

            state.event_map[0x7F]         = (Actions.IGNORE, None)
            return state

        if state_id == States.DCS_INTERMEDIATE:
            state = State(state_id)
            state.event_map[(0x00, 0x17)] = (Actions.IGNORE, None)
            state.event_map[0x19]         = (Actions.IGNORE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.IGNORE, None)

            state.event_map[(0x20, 0x2F)] = (Actions.COLLECT, None)

            state.event_map[(0x30, 0x3F)] = (None, States.DCS_IGNORE)

            state.event_map[(0x40, 0x7E)] = (None, States.DCS_PASSTHROUGH)

            state.event_map[0x7F]         = (Actions.IGNORE, None)
            return state

        if state_id == States.DCS_PASSTHROUGH:
            state = State(state_id)
            state.event_map['entry'] = (Actions.HOOK,)

            state.event_map[(0x00, 0x17)] = (Actions.PUT, None)
            state.event_map[0x19]         = (Actions.PUT, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.PUT, None)
            state.event_map[(0x20, 0x7E)] = (Actions.PUT, None)

            state.event_map[0x7F]         = (Actions.IGNORE, None)

            state.event_map['exit'] = (Actions.UNHOOK,)
            return state

        if state_id == States.DCS_IGNORE:
            state = State(state_id)
            state.event_map['entry'] = (Actions.HOOK,)

            state.event_map[(0x00, 0x17)] = (Actions.IGNORE, None)
            state.event_map[0x19]         = (Actions.IGNORE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.IGNORE, None)
            state.event_map[(0x20, 0x7F)] = (Actions.IGNORE, None)
            return state

        if state_id == States.OSC_STRING:
            state = State(state_id)
            state.event_map['entry'] = (Actions.OSC_START,)

            state.event_map[(0x00, 0x06)] = (Actions.IGNORE, None)
            state.event_map[(0x08, 0x17)] = (Actions.IGNORE, None)
            state.event_map[0x19]         = (Actions.IGNORE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.IGNORE, None)

            state.event_map[(0x20, 0x7F)] = (Actions.OSC_PUT, None)

            # XTerm accepts either BEL  or ST  for terminating OSC sequences
            # This is different from the VT500 Parser diagram by Paul Flo Williams
            state.event_map[0x07]         = (None, States.GROUND)

            state.event_map['exit'] = (Actions.OSC_END,)
            return state

        if state_id == States.SOS_PM_APC_STRING:
            state = State(state_id)
            state.event_map[(0x00, 0x17)] = (Actions.IGNORE, None)
            state.event_map[0x19]         = (Actions.IGNORE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.IGNORE, None)
            state.event_map[(0x20, 0x7F)] = (Actions.IGNORE, None)
            return state

        return None



class VT500Parser:
    """An implementation of a state machine for a parser for escape and control sequences,
     suitable for use in a VT emulator. Modeled after https://vt100.net/emu/dec_ansi_parser"""

    # Default NOP implementation of a terminal driver concerned with how codes are to be displayed
    class DefaultTerminalOutputHandler:
        def print(self, code):
            pass

        def execute(self, code):
            pass

    # Default NOP implementation of a ESC and CSI handler
    class DefaultControlSequenceHandler:
        def esc_dispatch(self, intermediate, final_code):
            pass

        def csi_dispatch(self, private_marker, parameters, intermediate, final_code):
            pass

    # Default NOP implementation of a Device Control dispatcher and handler
    # We do not differentiate between an dispatcher and multiple handler.
    # If the application requires that, it can pass different derived classes for that to the parser.
    class DefaultDcsHandler:
        def hook(self, private_marker, parameters, intermediate, final_code):
            return self

        def put(self, code):
            pass

        def end_of_data(self, code=None):
            pass

    # Default NOP implementation of a Operation System Control string handler
    class DefaultOscHandler:
        def start(self, code):
            pass

        def put(self, code):
            pass

        def end_of_data(self, code=None):
            pass

    def __init__(self):
        # Initialize handlers with default NOP implementations
        # These should be set by derived parsers with variants that do actual work
        self.terminal_output_handler = self.DefaultTerminalOutputHandler()
        self.control_sequence_handler = self.DefaultControlSequenceHandler()
        self.dc_control_handler = self.DefaultDcsHandler()
        self.osc_handler = self.DefaultOscHandler()

        # This is returned by the dc_control_handler.hook function
        self.dc_string_handler = self.dc_control_handler

        self.input_code = None
        self.private_flag = ''
        self.intermediate_char = ''
        self.final_char = ''
        self.parameter_string = ''

        self.state = State.get(States.GROUND)

        # Device control string. Buffered for statistics, because we can.
        self.device_control_string = ''
        # Operating system command. Buffered for statistics, because we can.
        self.operating_system_command = ''

        # We keep some statistics to see what we are dealing with in a file.
        self.states_visited = {States.GROUND: 1}
        self.actions_performed = {}
        self.control_functions_seen = {}
        self.escape_sequences_seen = {}
        self.control_sequences_seen = {}
        self.device_control_functions_seen = {}
        self.device_control_strings = set()
        self.os_commands = set()

    def perform_action(self, action, code):
        if action is None:
            return

        LOG.debug("{:02x} -> run action {}".format(code, action))
        method = getattr(self, action.value, self.default_action)
        method(code)
        self.stats_dict_inc(self.actions_performed, action)

    def default_action(self, code=None):
        LOG.warning("ENCOUNTERED AN UNIMPLEMENTED ACTION")

    def transition_to(self, new_state):
        LOG.info("Entering new state %s", new_state.id)
        self.state = new_state
        self.stats_dict_inc(self.states_visited, self.state.id)

    def input(self, code: int):
        # Send event to state
        LOG.debug("> %02x %s", code, "("+chr(code)+")" if 0x20 <= code <= 0x7E else '')
        action, new_state = self.state.event(code)

        # If a new state is returned,
        #  - run exit action of state, if any
        #  - run transition action, if any
        #  - set current state to new state
        #  - run entry action of new event, if any
        if isinstance(new_state, State):
            self.perform_action(self.state.exit(), code)
            self.perform_action(action, code)
            self.transition_to(new_state)
            self.perform_action(self.state.entry(), code)

        # If only an action was returned, execute the action
        elif action is not None:
            self.perform_action(action, code)

    # Implementation of the Actions
    def ignore(self, code=None):
        """The character or control is not processed.
         No observable difference in the terminal’s state would occur if the character that caused this action
         was not present in the input stream."""
        pass

    def print(self, code):
        """The current code should be mapped to a glyph according to the character set mappings and shift states
         in effect, and that glyph should be displayed."""

        self.terminal_output_handler.print(code)

    def execute(self, code):
        """The C0 or C1 control function should be executed, which may have any one of a variety of effects,
         including changing the cursor position, suspending or resuming communications or changing the
         shift states in effect. There are no parameters to this action."""
        self.stats_dict_inc(self.control_functions_seen, code)

        self.terminal_output_handler.execute(code)

    def clear(self, _code=None):
        """This action causes the current private flag, intermediate characters, final character
         and parameters to be forgotten."""
        self.private_flag = ''
        self.intermediate_char = ''
        self.final_char = ''
        self.parameter_string = ''

    def collect(self, code):
        """The private marker or intermediate character should be stored for later use in selecting
         a control function to be executed when a final character arrives. """
        # We want to differentiate between private markers and
        # intermediate characters. Not sure why.
        if 0x3c <= code <= 0x3f:
            self.private_flag = chr(code)
        else:
            self.intermediate_char += chr(code)

    def param(self, code):
        """This action collects the characters of a parameter string for a control sequence or device control sequence
         and builds a list of parameters. The characters processed by this action are the digits 0-9 (codes 30-39) and
         the semicolon (code 3B). The semicolon separates parameters."""
        self.parameter_string += chr(code)

    def esc_dispatch(self, code):
        """The final character of an escape sequence has arrived, so determined the control function to be executed
         from the intermediate character(s) and final character, and execute it. The intermediate characters are
         available because collect stored them as they arrived."""
        self.final_char += chr(code)
        self.stats_dict_inc(self.escape_sequences_seen, 'Esc' + self.private_flag + self.parameter_string
                                                        + self.intermediate_char + self.final_char)
        LOG.info("execute escape sequence: {}_{}".format(self.intermediate_char, self.final_char))

        self.control_sequence_handler.esc_dispatch(self.intermediate_char, self.final_char)

    def csi_dispatch(self, code):
        """A final character has arrived, so determine the control function to be executed from private marker,
         intermediate character(s) and final character, and execute it, passing in the parameter list."""
        self.final_char += chr(code)
        self.stats_dict_inc(self.control_sequences_seen, 'Esc[' + self.private_flag + self.parameter_string
                                                         + self.intermediate_char + self.final_char)
        LOG.info("determine control function from {}_{}_{}".format(self.private_flag,
                                                                   self.intermediate_char,
                                                                   self.final_char))
        LOG.info("execute with parameters: {}".format(self.parameter_string))

        self.control_sequence_handler.csi_dispatch(self.private_flag, self.parameter_string,
                                                   self.intermediate_char, self.final_char)

    def hook(self, code):
        """This action is invoked when a final character arrives in the first part of a device control string.
         It determines the control function from the private marker, intermediate character(s) and final character,
         and executes it, passing in the parameter list. It also selects a handler function for the rest of the
         characters in the control string. This handler function will be called by the put action for every character
         in the control string as it arrives."""
        self.final_char += chr(code)
        self.device_control_string = ''
        self.stats_dict_inc(self.device_control_functions_seen, 'EscP' + self.private_flag + self.parameter_string
                                                                + self.intermediate_char + self.final_char)
        LOG.info("determine control function from {}_{}_{}".format(self.private_flag,
                                                                   self.intermediate_char,
                                                                   self.final_char))
        LOG.info("execute with parameters: {}".format(self.parameter_string))
        LOG.info("Select handler function for following put actions")

        self.dc_string_handler = self.dc_control_handler.hook(self.private_flag, self.parameter_string,
                                                              self.intermediate_char, self.final_char)

    def put(self, code=None):
        """This action passes characters from the data string part of a device control string to a handler that
         has previously been selected by the hook action. C0 controls are also passed to the handler."""
        self.device_control_string += chr(code)

        self.dc_string_handler.put(code)

    def unhook(self, _code=None):
        """When a device control string is terminated by ST, CAN, SUB or ESC, this action calls the previously
         selected handler function with an “end of data” parameter. This allows the handler to finish neatly."""
        self.device_control_strings.add(self.device_control_string)
        LOG.info("Signal EOD to handler function")

        self.dc_string_handler.end_of_data()

    def osc_start(self, _code=None):
        """When the control function OSC (Operating System Command) is recognised, this action initializes
         an external parser (the “OSC Handler”) to handle the characters from the control string. OSC control strings
        are not structured in the same way as device control strings, so there is no choice of parsers."""
        self.operating_system_command = ''
        LOG.info("Initialize OSC handler")

        self.osc_handler.start(_code)

    def osc_put(self, code):
        """This action passes characters from the control string to the OSC Handler as they arrive.
         There is therefore no need to buffer characters until the end of the control string is recognised."""
        self.operating_system_command += chr(code)

        self.osc_handler.put(code)

    def osc_end(self, _code=None):
        """This action is called when the OSC string is terminated by ST, CAN, SUB or ESC,
         to allow the OSC handler to finish neatly."""
        self.os_commands.add(self.operating_system_command)
        LOG.info("Finish OSC handler")

        self.osc_handler.end_of_data()

    # Private helper functions
    def stats_dict_inc(self, stats_dict, code):
        """Increase count in map, or create new entry with count 0 if it doesn't exist yet."""
        if code in stats_dict:
            stats_dict[code] += 1
        else:
            stats_dict[code] = 1

    def log_statistics(self):
        """Gather statistics and dump to log"""
        LOG.info("##########################################################################")
        LOG.info("######                      S T A T I S T I C S                    #######")
        LOG.info("##########################################################################")

        LOG.info("-- Visited States:")
        for state in sorted(self.states_visited, key=self.states_visited.get, reverse=True):
            LOG.info(f"{state.name} : {self.states_visited[state]}")

        LOG.info("-- Executed Actions:")
        for action in sorted(self.actions_performed, key=self.actions_performed.get, reverse=True):
            LOG.info(f"{action.name} : {self.actions_performed[action]}")

        LOG.info("-- Control Functions:")
        for cf in sorted(self.control_functions_seen, key=self.control_functions_seen.get, reverse=True):
            LOG.info(f"{cf:02x} : {self.control_functions_seen[cf]}")

        LOG.info("-- Escape Sequences:")
        for key in sorted(self.escape_sequences_seen, key=self.escape_sequences_seen.get, reverse=True):
            LOG.info(f"{key} : {self.escape_sequences_seen[key]}")

        LOG.info("-- Control Sequences:")
        for key in sorted(self.control_sequences_seen, key=self.control_sequences_seen.get, reverse=True):
            LOG.info(f"{key} : {self.control_sequences_seen[key]}")

        LOG.info("-- Device Control Functions:")
        for key in sorted(self.device_control_functions_seen, key=self.device_control_functions_seen.get, reverse=True):
            LOG.info(f"{key} : {self.device_control_functions_seen[key]}")

        LOG.info("-- Device Control strings:")
        for dcs in self.device_control_strings:
            LOG.info(f"   {dcs}")

        LOG.info("-- Operating System Commands:")
        for osc in self.os_commands:
            LOG.info(f"   {osc}")


def parse(logfile):
    """Read the input file byte by byte and input the bytes to a VT500Parser instance"""
    parser = VT500Parser()
    c = logfile.read(1)
    while c:
        parser.input(ord(c))
        c = logfile.read(1)

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
