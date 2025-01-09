import random
from strategies.base_strategy import LoadBalancingStrategy


class RandomStrategy(LoadBalancingStrategy):
    def select_database(self, databases):
        if not databases:
            return None
        return random.choice(databases)
