from strategies.least_connections import LeastConnectionsStrategy
from strategies.random_strategy import  RandomStrategy
from strategies.round_robin import RoundRobinStrategy


class LoadBalancingStrategyFactory:
    @staticmethod
    def create_strategy(strategy_type):
        if strategy_type == "round_robin":
            return RoundRobinStrategy()
        elif strategy_type == "random":
            return RandomStrategy()
        elif strategy_type == "least_connections":
            return LeastConnectionsStrategy()
        else:
            raise ValueError(f"Unknown strategy type: {strategy_type}")
