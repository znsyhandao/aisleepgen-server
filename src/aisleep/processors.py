class BioSignalProcessor:
    def __init__(self, sample_rate, filters):
        self.sample_rate = sample_rate
        self.filters = filters

    def process_signal(self, signal_type, signal):
        if signal_type in self.filters:
            return self.filters[signal_type].apply(signal)
        return signal