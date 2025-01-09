import psycopg2
import json
from factory.strategy_factory import LoadBalancingStrategyFactory
from strategies.least_connections import LeastConnectionsStrategy
from logger.singleton_logger import SingletonLogger
from observer.base_observer import Observer


class LoadBalancer(Observer):
    def __init__(self, config_file, strategy_type="round_robin"):
        """
        Initialize the LoadBalancer with a configuration file and strategy type.
        :param config_file: Path to the JSON configuration file.
        :param strategy_type: The load balancing strategy type.
        """
        self.logger = SingletonLogger().get_logger()
        self.logger.info(f"Initializing LoadBalancer with strategy: {strategy_type}")
        self.config_file = config_file

        try:
            self.databases = self._load_config(config_file)
            if not self.databases:
                raise RuntimeError("No databases available in configuration.")
        except Exception as e:
            self.logger.error(f"Failed to load database configuration: {e}")
            raise

        try:
            self.strategy = LoadBalancingStrategyFactory.create_strategy(strategy_type)
            self.logger.info(f"Strategy '{strategy_type}' successfully initialized.")
        except ValueError as e:
            self.logger.error(f"Failed to initialize strategy: {e}")
            raise

    def _load_config(self, config_file):
        """
        Load the database configuration from a JSON file.
        :param config_file: Path to the JSON configuration file.
        :return: List of database configurations.
        """
        self.logger.info(f"Loading database configuration from {config_file}.")
        with open(config_file, 'r') as file:
            databases = json.load(file)
            if not databases:
                self.logger.warning("Configuration file contains no database entries.")
            self.logger.info("Database configuration loaded successfully.")
            return databases

    def get_connection(self):
        """
        Get a connection to a selected database based on the strategy.
        :return: psycopg2 connection object.
        """
        if not self.databases:
            self.logger.error("No databases available in configuration.")
            raise RuntimeError("No databases available in configuration.")

        db_info = self.strategy.select_database(self.databases)
        self.logger.debug(f"Selected database: {db_info['Name']}")

        conn_str = self._parse_connection_string(db_info["ConnectionString"])
        try:
            connection = psycopg2.connect(**conn_str)
            self.logger.info(f"Connected to database: {db_info['Name']}")
            return connection, db_info['Name']
        except psycopg2.OperationalError as e:
            self.logger.error(f"Failed to connect to {db_info['Name']}: {e}")
            return None, None

    def release_connection(self, db_name):
        """
        Release a connection, applicable for least_connections strategy.
        :param db_name: The name of the database to release the connection.
        """
        if isinstance(self.strategy, LeastConnectionsStrategy):
            self.strategy.release_connection(db_name)
            self.logger.debug(f"Released connection for database: {db_name}")

    def _parse_connection_string(self, conn_string):
        """
        Parse a connection string into a dictionary suitable for psycopg2.
        :param conn_string: The connection string.
        :return: Dictionary of connection parameters.
        """
        params = {}
        for pair in conn_string.split(';'):
            if pair.strip():
                try:
                    key, value = pair.split('=')
                    params[key.strip().lower()] = value.strip()
                except ValueError:
                    self.logger.error(f"Invalid connection string format: {pair}")
                    raise
        return params

    def set_strategy(self, strategy_type):
        """
        Change the load balancing strategy.
        :param strategy_type: The new strategy type.
        """
        try:
            self.strategy = LoadBalancingStrategyFactory.create_strategy(strategy_type)
            self.logger.info(f"Strategy changed to: {strategy_type}")
        except ValueError as e:
            self.logger.error(f"Failed to change strategy: {e}")
            raise

    def update(self, database_name, status):
        """
        Observer method to update the status of a database.
        :param database_name: Name of the database.
        :param status: The health status of the database ('healthy' or 'unhealthy').
        """
        if status == "unhealthy":
            self.logger.warning(f"Database {database_name} marked as unhealthy. Excluding from load balancing.")
            self.databases = [db for db in self.databases if db["Name"] != database_name]
        elif status == "healthy":
            # Re-add healthy database if it was removed
            if database_name not in [db["Name"] for db in self.databases]:
                self.logger.info(f"Database {database_name} marked as healthy. Including in load balancing.")
                with open(self.config_file, 'r') as file:
                    all_databases = json.load(file)
                    db_to_add = next((db for db in all_databases if db["Name"] == database_name), None)
                    if db_to_add:
                        self.databases.append(db_to_add)