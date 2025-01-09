from abc import ABC, abstractmethod


class Observer(ABC):
    @abstractmethod
    def update(self, database_name, status):
        """
        Update the observer with the current status of a database.
        :param database_name: Name of the database.
        :param status: The health status of the database (e.g., 'healthy', 'unhealthy').
        """
        pass
