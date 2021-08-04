import sys
from enum import Enum


class States(Enum):
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
    states = {}

    def __init__(self, id):
        # Textual id in case someone wants to find out who we are
        self.id = id
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
        # First check if the code is in the map as a single key
        if code in self.event_map:
            entry = self.event_map[code]
        else:
            # Otherwise find a range in the keys in which the code does fit
            for key in self.event_map:
                if isinstance(key, tuple):
                    if key[0] <= code <= key[1]:
                        entry = self.event_map[key]

        if entry is not None:
            action, state_id = entry
            return (action, None if state_id is None else self.get(state_id))

        return None

    def entry(self):
        if 'entry' in self.event_map:
            return self.event_map['entry'][0]
        return None

    def exit(self):
        if 'exit' in self.event_map:
            return self.event_map['exit'][0]
        return None

    @staticmethod
    def generate_state(name):
        if name == States.GROUND:
            state = State(name.value)
            state.event_map[(0x00, 0x17)] = (Actions.EXECUTE, None)
            state.event_map[0x19]         = (Actions.EXECUTE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.EXECUTE, None)

            state.event_map[(0x20, 0x7F)] = (Actions.PRINT, None)
            return state

        if name == States.ESCAPE:
            state = State(name.value)
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

        if name == States.ESCAPE_INTERMEDIATE:
            state = State(name.value)
            state.event_map[(0x00, 0x17)] = (Actions.EXECUTE, None)
            state.event_map[0x19]         = (Actions.EXECUTE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.EXECUTE, None)

            state.event_map[(0x20, 0x2F)] = (Actions.COLLECT, None)

            state.event_map[(0x30, 0x7E)] = (Actions.ESC_DISPATCH, States.GROUND)

            state.event_map[0x7F] = (Actions.IGNORE, None)
            return state

        if name == States.CSI_ENTRY:
            state = State(name.value)
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

        if name == States.CSI_PARAM:
            state = State(name.value)
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

        if name == States.CSI_INTERMEDIATE:
            state = State(name.value)
            state.event_map[(0x00, 0x17)] = (Actions.EXECUTE, None)
            state.event_map[0x19]         = (Actions.EXECUTE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.EXECUTE, None)

            state.event_map[(0x20, 0x2F)] = (Actions.COLLECT, None)

            state.event_map[(0x30, 0x3F)] = (None, States.CSI_IGNORE)

            state.event_map[(0x40, 0x7E)] = (Actions.CSI_DISPATCH, States.GROUND)

            state.event_map[0x7F]         = (Actions.IGNORE, None)
            return state

        if name == States.CSI_IGNORE:
            state = State(name.value)
            state.event_map[(0x00, 0x17)] = (Actions.EXECUTE, None)
            state.event_map[0x19]         = (Actions.EXECUTE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.EXECUTE, None)

            state.event_map[(0x20, 0x3F)] = (Actions.IGNORE, None)

            state.event_map[(0x40, 0x7E)] = (None, States.GROUND)

            state.event_map[0x7F]         = (Actions.IGNORE, None)
            return state

        if name == States.DCS_ENTRY:
            state = State(name.value)
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

        if name == States.DCS_PARAM:
            state = State(name.value)
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

        if name == States.DCS_INTERMEDIATE:
            state = State(name.value)
            state.event_map[(0x00, 0x17)] = (Actions.IGNORE, None)
            state.event_map[0x19]         = (Actions.IGNORE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.IGNORE, None)

            state.event_map[(0x20, 0x2F)] = (Actions.COLLECT, None)

            state.event_map[(0x30, 0x3F)] = (None, States.DCS_IGNORE)

            state.event_map[(0x40, 0x7E)] = (None, States.DCS_PASSTHROUGH)

            state.event_map[0x7F]         = (Actions.IGNORE, None)
            return state

        if name == States.DCS_PASSTHROUGH:
            state = State(name.value)
            state.event_map['entry'] = (Actions.HOOK,)

            state.event_map[(0x00, 0x17)] = (Actions.PUT, None)
            state.event_map[0x19]         = (Actions.PUT, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.PUT, None)
            state.event_map[(0x20, 0x7E)] = (Actions.PUT, None)

            state.event_map[0x7F]         = (Actions.IGNORE, None)

            state.event_map['exit'] = (Actions.UNHOOK,)
            return state

        if name == States.DCS_IGNORE:
            state = State(name.value)
            state.event_map['entry'] = (Actions.HOOK,)

            state.event_map[(0x00, 0x17)] = (Actions.IGNORE, None)
            state.event_map[0x19]         = (Actions.IGNORE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.IGNORE, None)
            state.event_map[(0x20, 0x7F)] = (Actions.IGNORE, None)
            return state

        if name == States.OSC_STRING:
            state = State(name.value)
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

        if name == States.SOS_PM_APC_STRING:
            state = State(name.value)
            state.event_map[(0x00, 0x17)] = (Actions.IGNORE, None)
            state.event_map[0x19]         = (Actions.IGNORE, None)
            state.event_map[(0x1C, 0x1F)] = (Actions.IGNORE, None)
            state.event_map[(0x20, 0x7F)] = (Actions.IGNORE, None)
            return state

        return None



class VT500Parser:
    def __init__(self):
        self.input_code = None
        self.private_flag = ''
        self.intermediate_char = ''
        self.final_char = ''
        self.parameter_string = ''

        self.state = State.get(States.GROUND)

    def run_action(self, action, code):
        if action is None:
            return

        print("{:02x} -> run action {}".format(code, action))
        method = getattr(self, action.value, self.default_action)
        method(code)

    def default_action(self, code=None):
        print("ENCOUNTERED AN UNIMPLEMENTED ACTION")

    def transition_to(self, new_state):
        print("Transition to new state", new_state.id)
        self.state = new_state

    def input(self, code: int):
        # Send event to state
        action, new_state = self.state.event(code)

        # If a new state is returned,
        #  - run exit action of state, if any
        #  - run transition action, if any
        #  - set current state to new state
        #  - run entry action of new event, if any
        if isinstance(new_state, State):
            self.run_action(self.state.exit(), code)
            self.run_action(action, code)
            self.transition_to(new_state)
            self.run_action(self.state.entry(), code)

        # If only an action was returned, execute the action
        elif action is not None:
            self.run_action(action, code)

    # Implementation of the Actions
    def ignore(self, code=None):
        pass

    def print(self, code):
        #sys.stdout.write(code)
        pass

    def execute(self, code):
        #sys.stdout.write(code)
        pass

    def clear(self, _code=None):
        self.private_flag = ''
        self.intermediate_char = ''
        self.final_char = ''
        self.parameter_string = ''

    def collect(self, code):
        # We want to differentiate between private markers and
        # intermediate characters. Not sure why.
        if 0x3c <= code <= 0x3f:
            self.private_flag = chr(code)
        else:
            self.intermediate_char += chr(code)

    def param(self, code):
        self.parameter_string += chr(code)

    def esc_dispatch(self, code):
        self.final_char += chr(code)
        print("execute escape sequence: {}_{}_{}_{}".format(self.private_flag, self.parameter_string,
                                                            self.intermediate_char, self.final_char))

    def csi_dispatch(self, code):
        self.final_char += chr(code)
        print("determine control function from {}_{}_{}".format(self.private_flag,
                                                                self.intermediate_char,
                                                                self.final_char))
        print("execute with parameters: {}".format(self.parameter_string))

    def hook(self, code=None):
        self.final_char += chr(code)
        print("determine control function from {}_{}_{}".format(self.private_flag,
                                                                self.intermediate_char,
                                                                self.final_char))
        print("execute with parameters: {}".format(self.parameter_string))
        print("Select handler function for following put actions")

    def put(self, code=None):
        pass

    def unhook(self, _code=None):
        print("Signal EOD to handler function")

    def osc_start(self, _code=None):
        print("Initialize OSC handler")

    def osc_put(self, code):
        pass

    def osc_end(self, _code=None):
        print("Finish OSC handler")


def parse(logfile):
    parser = VT500Parser()
    c = logfile.read(1)
    while c:
        parser.input(ord(c))
        c = logfile.read(1)


def main():
    if len(sys.argv) <= 1:
        print("Log file missing. Specify log file to parse.")
        exit()

    with open(sys.argv[1], 'r') as logfile:
        parse(logfile)


if __name__ == '__main__':
    main()
