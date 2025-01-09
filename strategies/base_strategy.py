from abc import ABC, abstractmethod


class LoadBalancingStrategy(ABC):
    @abstractmethod
    def select_database(self, databases):
        """
        Select a database according to the strategy.
        :param databases: List of database configurations.
        :return: Selected database configuration.
        """
        pass
    