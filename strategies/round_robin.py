from strategies.base_strategy import LoadBalancingStrategy


class RoundRobinStrategy(LoadBalancingStrategy):
    def __init__(self):
        self.index = 0

    def select_database(self, databases):
        if not databases:
            return None
        server = databases[self.index]
        self.index = (self.index + 1) % len(databases)
        return server
