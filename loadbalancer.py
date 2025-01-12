import time
import psycopg2
import json
from factory.strategy_factory import LoadBalancingStrategyFactory
from logger.singleton_logger import SingletonLogger
from observer.base_observer import Observer


class LoadBalancer(Observer):
    def __init__(self, config_file, strategy_type="round_robin"):
        self.logger = SingletonLogger().get_logger()
        self.logger.info(f"Initializing LoadBalancer with strategy: {strategy_type}")
        self.config_file = config_file
        self.databases = self.load_active_databases()
        self.strategy = self.set_strategy(strategy_type)

    def load_active_databases(self):
        """
        Load the database configuration from a JSON file and validate connectivity.
        :return: List of active database configurations.
        """
        self.logger.info(f"Loading database configuration from {self.config_file}.")
        try:
            with open(self.config_file, 'r') as file:
                all_databases = json.load(file)

            active_databases = []
            inactive_databases = []

            for db in all_databases:
                conn_str = self._parse_connection_string(db["ConnectionString"])
                if self._is_database_active(conn_str):
                    active_databases.append(db)
                    self.logger.info(f"Database {db['Name']} is active and added to the configuration.")
                else:
                    inactive_databases.append(db["Name"])

            if inactive_databases:
                self.logger.warning(f"The following databases are inactive and will not be used: {', '.join(inactive_databases)}")

            if not active_databases:
                raise ValueError("No active databases available in the configuration.")

            return active_databases
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.logger.error(f"Error loading configuration: {e}")
            raise

    def _is_database_active(self, conn_str):
        """
        Check if a database is active by attempting a connection.
        :param conn_str: Connection string parameters as a dictionary.
        :return: True if the database is active, False otherwise.
        """
        try:
            with psycopg2.connect(**conn_str) as conn:
                self.logger.debug("Successfully connected to database.")
                return True
        except psycopg2.OperationalError as e:
            self.logger.error(f"Database connection failed: {e}")
            return False

    def set_strategy(self, strategy_type):
        """
        Set the load balancing strategy based on the strategy type.
        """
        try:
            strategy = LoadBalancingStrategyFactory.create_strategy(strategy_type)
            self.logger.info(f"Strategy '{strategy_type}' successfully initialized.")
            return strategy
        except KeyError as e:
            self.logger.error(f"Unknown strategy type: {strategy_type} - {e}")
            raise

    def get_connection(self):
        """
        Get a connection to the selected database.
        """
        if not self.databases:
            self.logger.error("No databases available in configuration.")
            raise RuntimeError("No databases available in configuration.")

        db_info = self.strategy.select_database(self.databases)
        self.logger.debug(f"Selected database: {db_info['Name']}")

        conn_str = self._parse_connection_string(db_info["ConnectionString"])
        try:
            self.logger.info(f"Connected to database: {db_info['Name']}")
            connection = psycopg2.connect(**conn_str)
            return connection, db_info['Name']
        except psycopg2.OperationalError as e:
            self.logger.error(f"Failed to connect to {db_info['Name']}: {e}")
            return None, None

    def create_table(self, schema):
        """
        Create a table in all active databases.
        """
        for db in self.databases:
            conn_str = self._parse_connection_string(db["ConnectionString"])
            conn = None
            try:
                conn = psycopg2.connect(**conn_str)
                with conn.cursor() as cursor:
                    cursor.execute(schema)
                    conn.commit()
                    self.logger.info(f"Table created in database {db['Name']}")
            except Exception as e:
                self.logger.error(f"Error creating table in database {db['Name']}: {e}")
            finally:
                if conn:
                    conn.close()

    def reset_sequences(self):
        """
        Reset sequences for a specific table in all active databases.
        """
        query = "SELECT setval(pg_get_serial_sequence('users', 'id'), COALESCE(MAX(id), 0), true) FROM users;"
        for db in self.databases:
            conn_str = self._parse_connection_string(db["ConnectionString"])
            conn = None
            try:
                conn = psycopg2.connect(**conn_str)
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    conn.commit()
            except Exception as e:
                self.logger.error(f"Error resetting sequence in database {db['Name']}: {e}")
            finally:
                if conn:
                    conn.close()

    def execute_select(self, query, params=None):
        """
        Execute a SELECT query on a single active database selected by the strategy.
        """
        conn, db_name = self.get_connection()
        if conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    result = cursor.fetchall()
                    return result
            except Exception as e:
                self.logger.error(f"Error executing SELECT on {db_name}: {e}")
            finally:
                conn.close()

    def execute_non_select_query(self, query, params=None):
        """
        Execute a non-SELECT query on all active databases.
        """
        for db in self.databases:
            conn_str = self._parse_connection_string(db["ConnectionString"])
            conn = None
            try:
                conn = psycopg2.connect(**conn_str)
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    conn.commit()
                    self.logger.info(f"Query executed on database {db['Name']}: {query}")
            except Exception as e:
                self.logger.error(f"Error executing query on database {db['Name']}: {e}")
            finally:
                if conn:
                    conn.close()

    def monitor_new_databases(self, interval=60):
        """
        Regularly check for new databases in the configuration file and add them if active.
        """
        while True:
            try:
                with open(self.config_file, 'r') as file:
                    all_databases = json.load(file)

                for db in all_databases:
                    if db["Name"] not in [d["Name"] for d in self.databases]:
                        self.add_database(db)
            except Exception as e:
                self.logger.error(f"Error while monitoring new databases: {e}")

            time.sleep(interval)

    def add_database(self, database_config):
        """
        Add a new database to the configuration if it is active.
        """
        conn_str = self._parse_connection_string(database_config["ConnectionString"])
        if self._is_database_active(conn_str):
            self.databases.append(database_config)
            self.logger.info(f"New database added: {database_config['Name']}")
        else:
            self.logger.warning(f"Database {database_config['Name']} is inactive and will not be added.")

    def _parse_connection_string(self, conn_string):
        """
        Parse the connection string into a dictionary of parameters.
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

    def update(self, database_name, status):
        """
        Update the status of a database (healthy/unhealthy).
        """
        if status == "unhealthy":
            self.logger.warning(f"Database {database_name} marked as unhealthy. Excluding from load balancing.")
            self.databases = [db for db in self.databases if db["Name"] != database_name]
        elif status == "healthy":
            with open(self.config_file, 'r') as file:
                all_databases = json.load(file)
                db_to_add = next((db for db in all_databases if db["Name"] == database_name), None)
                if db_to_add:
                    self.add_database(db_to_add)
