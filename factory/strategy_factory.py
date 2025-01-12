from strategies.least_connections import LeastConnectionsStrategy
from strategies.random_strategy import  RandomStrategy
from strategies.round_robin import RoundRobinStrategy


class LoadBalancingStrategyFactory:
    @staticmethod
    def create_strategy(strategy_type):
        strategies = {
            "round_robin": RoundRobinStrategy,
            "random": RandomStrategy,
            "least_connections": LeastConnectionsStrategy,
        }
        try:
            return strategies[strategy_type]()
        except KeyError:
            raise ValueError(f"Unknown strategy type: {strategy_type}")
