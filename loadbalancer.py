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
        self.logger.info(f"Loading database configuration from {config_file}.")
        with open(config_file, 'r') as file:
            databases = json.load(file)
            if not databases:
                self.logger.warning("Configuration file contains no database entries.")
            self.logger.info("Database configuration loaded successfully.")
            return databases

    def get_connection(self):
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

    def reset_sequences(self):
        """
        Reset sequences for the 'id' column in all databases to match the current max(id).
        """
        query = "SELECT setval(pg_get_serial_sequence('users', 'id'), COALESCE(MAX(id), 0), true) FROM users;"
        for db in self.databases:
            conn_str = self._parse_connection_string(db["ConnectionString"])
            try:
                conn = psycopg2.connect(**conn_str)
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    conn.commit()
                    # self.logger.info(f"Sequence reset in database {db['Name']}")
            except Exception as e:
                self.logger.error(f"Error resetting sequence in database {db['Name']}: {e}")
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
                    # self.logger.info(f"SELECT executed on database {db_name}: {result}")
                    return result
            except Exception as e:
                self.logger.error(f"Error executing SELECT on {db_name}: {e}")
            finally:
                conn.close()

    def execute_query_on_all_databases(self, query, params=None):
        """
        Execute a query on all available databases.
        """
        for db in self.databases:
            conn_str = self._parse_connection_string(db["ConnectionString"])
            try:
                conn = psycopg2.connect(**conn_str)
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    conn.commit()
                    self.logger.info(f"Query executed on database {db['Name']}")
            except Exception as e:
                self.logger.error(f"Error executing query on database {db['Name']}: {e}")
            finally:
                if conn:
                    conn.close()

    def add_user(self, name, email):
        """
        Add a new user to all databases.
        """
        query = "INSERT INTO users (name, email) VALUES (%s, %s);"
        self.execute_query_on_all_databases(query, (name, email))
        self.logger.info(f"User added to all databases: Name={name}, Email={email}")

    def update_user(self, user_id, name=None, email=None):
        """
        Update user details in all databases, only if the user ID exists.
        """
        # Sprawdzenie, czy użytkownik istnieje w tabeli w jednej z baz danych
        query_check = "SELECT 1 FROM users WHERE id = %s LIMIT 1;"
        user_exists = False

        for db in self.databases:
            conn_str = self._parse_connection_string(db["ConnectionString"])
            try:
                conn = psycopg2.connect(**conn_str)
                with conn.cursor() as cursor:
                    cursor.execute(query_check, (user_id,))
                    if cursor.fetchone():
                        user_exists = True
                        print(f"Użytkownik o ID {user_id} został zaktualizowany.")
                        break  # Użytkownik znaleziony, przerwij sprawdzanie
            except Exception as e:
                self.logger.error(f"Error checking user existence in database {db['Name']}: {e}")
            finally:
                if conn:
                    conn.close()

        if not user_exists:
            # self.logger.warning(f"User with ID {user_id} does not exist in any database.")
            print(f"Użytkownik o ID {user_id} nie istnieje.")
            return

        # Budowanie zapytania UPDATE tylko jeśli użytkownik istnieje
        query = "UPDATE users SET "
        params = []
        if name:
            query += "name = %s, "
            params.append(name)
        if email:
            query += "email = %s, "
            params.append(email)
        query = query.rstrip(", ") + " WHERE id = %s;"
        params.append(user_id)

        self.execute_query_on_all_databases(query, params)
        self.logger.info(f"User updated in all databases: ID={user_id}, Name={name}, Email={email}")

    def delete_user(self, user_id):
        """
        Delete a user from all databases if the user ID exists, and reset sequences.
        """
        # Sprawdzenie, czy użytkownik istnieje w tabeli w jednej z baz danych
        query_check = "SELECT 1 FROM users WHERE id = %s LIMIT 1;"
        user_exists = False

        for db in self.databases:
            conn_str = self._parse_connection_string(db["ConnectionString"])
            try:
                conn = psycopg2.connect(**conn_str)
                with conn.cursor() as cursor:
                    cursor.execute(query_check, (user_id,))
                    if cursor.fetchone():
                        user_exists = True
                        break  # Przerwij sprawdzanie, jeśli użytkownik został znaleziony
            except Exception as e:
                self.logger.error(f"Error checking user existence in database {db['Name']}: {e}")
            finally:
                if conn:
                    conn.close()

        if not user_exists:
            # self.logger.warning(f"User with ID {user_id} does not exist.")
            print(f"Użytkownik o ID {user_id} nie istnieje.")
            return

        # Usuń użytkownika z wszystkich baz danych
        query_delete = "DELETE FROM users WHERE id = %s;"
        self.execute_query_on_all_databases(query_delete, (user_id,))
        self.logger.info(f"User deleted from all databases: ID={user_id}")
        print(f"Użytkownik o ID {user_id} został usunięty.")

        # Resetuj sekwencje po usunięciu użytkownika
        self.reset_sequences()

    def add_database(self, database_config):
        """
        Add a new database to the configuration and synchronize its data.
        """
        self.databases.append(database_config)
        self.logger.info(f"New database added: {database_config['Name']}")

        conn_str = self._parse_connection_string(database_config["ConnectionString"])
        try:
            conn = psycopg2.connect(**conn_str)
            with conn.cursor() as cursor:
                # Create the users table if not exists
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL
                );
                """)
                conn.commit()
                self.logger.info(f"Table created in new database {database_config['Name']}")
        except Exception as e:
            self.logger.error(f"Error adding new database {database_config['Name']}: {e}")
        finally:
            if conn:
                conn.close()

    def set_strategy(self, strategy_type):
        try:
            self.strategy = LoadBalancingStrategyFactory.create_strategy(strategy_type)
            self.logger.info(f"Strategy changed to: {strategy_type}")
        except ValueError as e:
            self.logger.error(f"Failed to change strategy: {e}")
            raise

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
            self.databases = [db for db in self.databases if db["Name"] != database_name]
        elif status == "healthy":
            if database_name not in [db["Name"] for db in self.databases]:
                self.logger.info(f"Database {database_name} marked as healthy. Including in load balancing.")
                with open(self.config_file, 'r') as file:
                    all_databases = json.load(file)
                    db_to_add = next((db for db in all_databases if db["Name"] == database_name), None)
                    if db_to_add:
                        self.databases.append(db_to_add)
