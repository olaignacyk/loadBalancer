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

    def create_table(self, schema):
        """
        Create a table in all databases.
        :param schema: The SQL schema to execute.
        """
        for db in self.databases:
            conn_str = self._parse_connection_string(db["ConnectionString"])
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

    def execute_select(self, query, params=None):
        """
        Execute a SELECT query on a database chosen by the strategy.
        :param query: The SELECT query to execute.
        :param params: Optional query parameters.
        :return: Query results.
        """
        conn, db_name = self.get_connection()
        if conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    result = cursor.fetchall()
                    self.logger.info(f"SELECT executed on database {db_name}: {result}")
                    return result
            except Exception as e:
                self.logger.error(f"Error executing SELECT on {db_name}: {e}")
            finally:
                conn.close()

    def synchronize_tables(self, master_file):
        """
        Synchronize all databases with data from the master file.
        :param master_file: Path to the master JSON file containing the table data.
        """
        with open(master_file, 'r') as file:
            master_data = json.load(file)

        for db in self.databases:
            conn_str = self._parse_connection_string(db["ConnectionString"])
            try:
                conn = psycopg2.connect(**conn_str)
                with conn.cursor() as cursor:
                    # Clear existing data
                    cursor.execute("DELETE FROM users;")

                    # Insert master data
                    for record in master_data:
                        cursor.execute(
                            "INSERT INTO users (id, name, email) VALUES (%s, %s, %s) "
                            "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, email = EXCLUDED.email;",
                            (record["id"], record["name"], record["email"])
                        )
                    conn.commit()
                    self.logger.info(f"Database {db['Name']} synchronized with master data.")
            except Exception as e:
                self.logger.error(f"Error synchronizing database {db['Name']}: {e}")
            finally:
                if conn:
                    conn.close()

    def add_user(self, master_file, name, email):
        """
        Add a new user to the master data and synchronize with all databases.
        :param master_file: Path to the master JSON file.
        :param name: Name of the user.
        :param email: Email of the user.
        """
        with open(master_file, 'r+') as file:
            data = json.load(file)
            new_id = max([user["id"] for user in data]) + 1 if data else 1
            new_user = {"id": new_id, "name": name, "email": email}
            data.append(new_user)

            # Write back to the file
            file.seek(0)
            json.dump(data, file, indent=4)
            file.truncate()

        self.logger.info(f"Added new user to master data: {new_user}")
        self.synchronize_tables(master_file)

    def update_user(self, master_file, user_id, name=None, email=None):
        """
        Update a user's details in the master data and synchronize with all databases.
        :param master_file: Path to the master JSON file.
        :param user_id: ID of the user to update.
        :param name: New name for the user.
        :param email: New email for the user.
        """
        with open(master_file, 'r+') as file:
            data = json.load(file)
            for user in data:
                if user["id"] == user_id:
                    if name:
                        user["name"] = name
                    if email:
                        user["email"] = email
                    break
            else:
                self.logger.error(f"User with ID {user_id} not found.")
                return

            # Write back to the file
            file.seek(0)
            json.dump(data, file, indent=4)
            file.truncate()

        self.logger.info(f"Updated user in master data: {user_id}")
        self.synchronize_tables(master_file)

    def delete_user(self, master_file, user_id):
        """
        Delete a user from the master data and synchronize with all databases.
        :param master_file: Path to the master JSON file.
        :param user_id: ID of the user to delete.
        """
        with open(master_file, 'r+') as file:
            data = json.load(file)
            data = [user for user in data if user["id"] != user_id]

            # Write back to the file
            file.seek(0)
            json.dump(data, file, indent=4)
            file.truncate()

        self.logger.info(f"Deleted user from master data: {user_id}")
        self.synchronize_tables(master_file)

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
            if database_name not in [db["Name"] for db in self.databases]:
                self.logger.info(f"Database {database_name} marked as healthy. Including in load balancing.")
                with open(self.config_file, 'r') as file:
                    all_databases = json.load(file)
                    db_to_add = next((db for db in all_databases if db["Name"] == database_name), None)
                    if db_to_add:
                        self.databases.append(db_to_add)
