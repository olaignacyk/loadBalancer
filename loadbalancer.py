import psycopg2
import json
from factory.strategy_factory import LoadBalancingStrategyFactory
from logger.singleton_logger import SingletonLogger
from observer.base_observer import Observer


class LoadBalancer(Observer):
    def __init__(self, config_file, table_name, strategy_type="round_robin"):
        self.table_name = table_name
        self.logger = SingletonLogger().get_logger()
        self.logger.info(f"Initializing LoadBalancer with strategy: {strategy_type}")
        self.config_file = config_file
        self.databases = self.load_config()
        self.active_databases = self.databases.copy()
        self.strategy = LoadBalancingStrategyFactory.create_strategy(strategy_type)

    def load_config(self):
        """
        Load the database configuration from a JSON file.
        :return: List of database configurations.
        """
        self.logger.info(f"Loading database configuration from {self.config_file}.")
        try:
            with open(self.config_file, 'r') as file:
                databases = json.load(file)
            if not databases:
                raise ValueError("Configuration file is empty or invalid.")
            return databases
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.logger.error(f"Error loading configuration: {e}")
            raise

    def set_strategy(self, strategy_type):
        try:
            self.strategy = LoadBalancingStrategyFactory.create_strategy(strategy_type)
            self.logger.info(f"Strategy changed to: {strategy_type}")
        except ValueError as e:
            self.logger.error(f"Failed to change strategy: {e}")
            raise

    def get_connection(self):
        if not self.active_databases:
            self.logger.error("No active databases available.")
            raise RuntimeError("No active databases available.")

        db_info = self.strategy.select_database(self.active_databases)
        self.logger.debug(f"Selected database: {db_info['Name']}")

        conn_str = self._parse_connection_string(db_info["ConnectionString"])
        try:
            self.logger.info(f"Connected to database: {db_info['Name']}")
            connection = psycopg2.connect(**conn_str)
            return connection, db_info['Name']
        except psycopg2.OperationalError as e:
            self.logger.error(f"Failed to connect to {db_info['Name']}: {e}")
            self.update(db_info['Name'], status="unhealthy")
            return None, None

    def create_table(self, schema):
        """
        Create a table in all active databases.
        """
        for db in self.active_databases:
            conn_str = self._parse_connection_string(db["ConnectionString"])
            conn = None
            try:
                conn = psycopg2.connect(**conn_str)
                with conn.cursor() as cursor:
                    cursor.execute(schema)
                    conn.commit()
                    self.logger.info(f"Table created in database {db['Name']}")
            except psycopg2.OperationalError:
                self.logger.warning(f"Could not connect to database {db['Name']}. Skipping table creation.")
            except Exception as e:
                self.logger.error(f"Error creating table in database {db['Name']}: {e}")
            finally:
                if conn:
                    conn.close()

    def reset_sequences(self):
        query = "SELECT setval(pg_get_serial_sequence('users', 'id'), COALESCE(MAX(id), 0), true) FROM users;"
        for db in self.active_databases:
            conn_str = self._parse_connection_string(db["ConnectionString"])
            conn = None
            try:
                conn = psycopg2.connect(**conn_str)
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    conn.commit()
            except Exception as e:
                # self.logger.error(f"Error resetting sequence in database {db['Name']}: {e}")
                pass
            finally:
                if conn:
                    conn.close()

    def execute_select(self, query, params=None):
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
        for db in self.active_databases:
            conn_str = self._parse_connection_string(db["ConnectionString"])
            conn = None
            try:
                conn = psycopg2.connect(**conn_str)
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    conn.commit()
                    self.logger.info(f"Query executed on active database {db['Name']}")
                    self.reset_sequences()
            except Exception as e:
                self.logger.error(f"Error executing query on database {db['Name']}: {e}")
            finally:
                if conn:
                    conn.close()

    def synchronize_tables(self, table_name):
        """
        Synchronize data in a specified table across all active databases.
        The database with the most consistent data across all databases is used as the source.
        :param table_name: Name of the table to synchronize.
        """
        if not self.active_databases:
            self.logger.warning("No active databases to synchronize.")
            return

        # Step 1: Fetch column information and data from all active databases
        database_data = {}
        table_columns = None
        for db in self.active_databases:
            conn_str = self._parse_connection_string(db["ConnectionString"])
            conn = None
            try:
                conn = psycopg2.connect(**conn_str)
                with conn.cursor() as cursor:
                    # Fetch column information
                    if table_columns is None:
                        cursor.execute(f"""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = %s
                        ORDER BY ordinal_position;
                        """, (table_name,))
                        columns = cursor.fetchall()
                        if not columns:
                            self.logger.warning(f"Table '{table_name}' does not exist in database '{db['Name']}'.")
                            return
                        table_columns = [col[0] for col in columns]

                    cursor.execute(f"SELECT * FROM {table_name} ORDER BY {table_columns[0]};")
                    data = cursor.fetchall()
                    database_data[db["Name"]] = data
            except psycopg2.Error as e:
                self.logger.warning(f"Error fetching data from database '{db['Name']}': {e}")
            finally:
                if conn:
                    conn.close()

        if not database_data:
            self.logger.warning(f"No valid data fetched for table '{table_name}' from active databases.")
            return

        # Step 2: Determine the most consistent database (by comparing data sets)
        reference_db_name = None
        max_matches = 0
        for db_name, data in database_data.items():
            matches = sum(
                1 for other_db, other_data in database_data.items() if db_name != other_db and data == other_data
            )
            if matches > max_matches:
                max_matches = matches
                reference_db_name = db_name

        if not reference_db_name:
            self.logger.error(
                f"Failed to determine the most consistent database for synchronization of '{table_name}'.")
            return

        reference_data = database_data[reference_db_name]
        self.logger.info(
            f"Database '{reference_db_name}' selected as the source for synchronizing table '{table_name}'.")

        # Step 3: Update all other active databases
        for db in self.active_databases:
            if db["Name"] == reference_db_name:
                continue  # Skip the source database
            conn_str = self._parse_connection_string(db["ConnectionString"])
            conn = None
            try:
                conn = psycopg2.connect(**conn_str)
                with conn.cursor() as cursor:
                    cursor.execute(f"DELETE FROM {table_name};")

                    insert_query = f"""
                    INSERT INTO {table_name} ({', '.join(table_columns)}) 
                    VALUES ({', '.join(['%s'] * len(table_columns))})
                    ON CONFLICT ({table_columns[0]}) 
                    DO UPDATE SET {', '.join([f"{col} = EXCLUDED.{col}" for col in table_columns[1:]])};
                    """
                    for row in reference_data:
                        cursor.execute(insert_query, row)
                    conn.commit()
                self.logger.info(
                    f"Synchronized database '{db['Name']}' with data from '{reference_db_name}' for table '{table_name}'.")
            except psycopg2.Error as e:
                self.logger.warning(f"Error synchronizing database '{db['Name']}' for table '{table_name}': {e}")
            finally:
                if conn:
                    conn.close()

    def _parse_connection_string(self, conn_string):
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
        if status == "unhealthy":
            self.logger.warning(f"Database {database_name} marked as unhealthy. Excluding from load balancing.")
            self.active_databases = [db for db in self.active_databases if db["Name"] != database_name]
        elif status == "healthy":
            if database_name not in [db["Name"] for db in self.active_databases]:
                self.logger.info(f"Database {database_name} marked as healthy. Including in load balancing.")
                db_to_add = next((db for db in self.databases if db["Name"] == database_name), None)
                if db_to_add:
                    self.active_databases.append(db_to_add)
                    self.synchronize_tables(self.table_name)
