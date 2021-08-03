import sys


class State:
    states = {}

    def __init__(self):
        # The event map defines for each input code a (action,state) tuple.
        # The tuple has an action if the event, i.e. input code, results
        # in an action, and it has a state if the event results in a
        # transition to a new state.
        # The keys of the map can be single codes, or tuples that define a
        # start and an end of a code range.
        self.event_map = {
            # The CANcel and SUBstitute control codes are immediately executed
            # and always transition to 'ground'
            0x18: ('execute', 'ground'),
            0x1A: ('execute', 'ground'),
            # The ESCape code always starts a escape control, i.e. transition to 'escape'
            0x1B: (None,      'escape'),
            # The following C1 controls get executed immediately and transition to 'ground'
            (0x80, 0x8F): ('execute', 'ground'),
            (0x91, 0x97): ('execute', 'ground'),
            0x99: ('execute', 'ground'),
            0x9A: ('execute', 'ground'),
            # The SOS, PM and APC control functions are ignored and immediately transition
            # to 'sos_pm_apc_string' for that.
            0x98: (None, 'sos_pm_apc_string'),
            0x9E: (None, 'sos_pm_apc_string'),
            0x9F: (None, 'sos_pm_apc_string'),
            # The Device Control String control function always starts a new device control string
            0x90: (None, 'dcs_entry'),
            # The Control String Initiator control function always starts a new control string
            0x9B: (None, 'csi_entry'),
            # The Operating System Command control function always starts a new OSC string
            0x9D: (None, 'ocs_entry')
        }

    @classmethod
    def get(cls, name):
        if name in cls.states:
            return cls.states[name]
        else:
            state = generate_state(name)
            cls.states[name] = state
            return state

    def event(self, code):
        return None

    def entry(self):
        return None

    def exit(self):
        return None

    def transition(self, name):
        return None


def generate_state(name):
    if name == 'ground':
        state = State()
        state.event_map[(0x00, 0x17)] = ('execute', None)
        state.event_map[0x19]         = ('execute', None)
        state.event_map[(0x1C, 0x1F)] = ('execute', None)

        state.event_map[(0x20, 0x7F)] = ('print', None)
        return state

    if name == 'escape':
        state = State()
        state.event_map['entry'] = ('clear', None)

        state.event_map[(0x00, 0x17)] = ('execute', None)
        state.event_map[0x19]         = ('execute', None)
        state.event_map[(0x1C, 0x1F)] = ('execute', None)

        state.event_map[(0x20, 0x2F)] = ('collect', 'escape_intermediate')

        state.event_map[(0x30, 0x4F)] = ('esc_dispatch', 'ground')
        state.event_map[(0x51, 0x57)] = ('esc_dispatch', 'ground')
        state.event_map[0x59]         = ('esc_dispatch', 'ground')
        state.event_map[0x5A]         = ('esc_dispatch', 'ground')
        state.event_map[0x5C]         = ('esc_dispatch', 'ground')
        state.event_map[(0x60, 0x7E)] = ('esc_dispatch', 'ground')

        state.event_map[0x58] = (None, 'sos_pm_apc_string')
        state.event_map[0x5E] = (None, 'sos_pm_apc_string')
        state.event_map[0x5F] = (None, 'sos_pm_apc_string')

        state.event_map[0x50] = (None, 'dcs_entry')
        state.event_map[0x5B] = (None, 'csi_entry')
        state.event_map[0x5D] = (None, 'osc_string')

        state.event_map[0x7F] = ('ignore', None)
        return state

    return None



class VT500Parser:
    def __init__(self):
        self.private_flag = None
        self.intermediate_char = None
        self.final_char = None
        self.parameter_string = None

        self.state = State.get('ground')

    def reset(self):
        self.private_flag = None
        self.intermediate_char = None
        self.final_char = None
        self.parameter_string = None

    def run_action(self, name):
        print("Run", name)

    def input(self, code):
        # Send event to state
        result = self.state.event(code)

        # If state returns a new state
        #  - run exit action of state, if any
        #  - run transition action, if any
        #  - set current state to new state
        #  - run entry action of new event, if any
        if isinstance(result, State):
            self.run_action(self.state.exit())
            self.run_action(self.state.transition(result))
            self.state = result
            self.run_action(self.state.entry())
        # If this is not None, then an action was returned
        elif result is not None:
            self.run_action(result)


def parse(logfile):
    parser = VT500Parser()
    c = logfile.read(1)
    while c:
        parser.input(c)


def main():
    if len(sys.argv) <= 1:
        print("Log file missing. Specify log file to parse.")
        exit()

    with open(sys.argv[1], 'r') as logfile:
        parse(logfile)


if __name__ == '__main__':
    main()
