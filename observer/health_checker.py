import psycopg2
from threading import Timer
from logger.singleton_logger import SingletonLogger


class HealthChecker:
    def __init__(self, databases, check_interval=10):
        """
        Initialize the HealthChecker.
        :param databases: List of database configurations.
        :param check_interval: Time interval (in seconds) between health checks.
        """
        self.databases = databases
        self.observers = []
        self.logger = SingletonLogger().get_logger()
        self.check_interval = check_interval
        self.timer = None
        self.database_status = {db["Name"]: "unknown" for db in databases}

    def add_observer(self, observer):
        """
        Add an observer to the list.
        :param observer: An object implementing the Observer interface.
        """
        self.observers.append(observer)
        self.logger.info(f"Observer {observer.__class__.__name__} added.")

    def remove_observer(self, observer):
        """
        Remove an observer from the list.
        :param observer: The observer to remove.
        """
        self.observers.remove(observer)
        self.logger.info(f"Observer {observer.__class__.__name__} removed.")

    def notify_observers(self, database_name, status):
        """
        Notify all observers about the health status of a database.
        :param database_name: Name of the database.
        :param status: The health status of the database.
        """
        for observer in self.observers:
            observer.update(database_name, status)

    def initial_health_check(self):
        """
        Perform an initial health check for all databases.
        """
        self.logger.info("Performing initial health check...")
        for db in self.databases:
            db_name = db["Name"]
            conn_str = self._parse_connection_string(db["ConnectionString"])
            try:
                conn = psycopg2.connect(**conn_str)
                conn.close()
                self.logger.info(f"Database {db_name} is healthy.")
                self.database_status[db_name] = "healthy"
                self.notify_observers(db_name, "healthy")
            except psycopg2.OperationalError:
                self.logger.error(f"Database {db_name} is unhealthy.")
                self.database_status[db_name] = "unhealthy"
                self.notify_observers(db_name, "unhealthy")

    def check_health(self):
        """
        Monitor databases and notify observers only when a status change occurs.
        """
        # self.logger.info("Monitoring database health...")
        for db in self.databases:
            db_name = db["Name"]
            conn_str = self._parse_connection_string(db["ConnectionString"])

            try:
                conn = psycopg2.connect(**conn_str)
                conn.close()
                if self.database_status[db_name] != "healthy":
                    self.logger.info(f"Database {db_name} status changed to healthy.")
                    self.database_status[db_name] = "healthy"
                    self.notify_observers(db_name, "healthy")
            except psycopg2.OperationalError:
                if self.database_status[db_name] != "unhealthy":
                    self.logger.error(f"Database {db_name} status changed to unhealthy.")
                    self.database_status[db_name] = "unhealthy"
                    self.notify_observers(db_name, "unhealthy")

        # Schedule the next health check
        self.timer = Timer(self.check_interval, self.check_health)
        self.timer.start()

    def _parse_connection_string(self, conn_string):
        """
        Parse a connection string into a dictionary suitable for psycopg2.
        """
        params = {}
        for pair in conn_string.split(";"):
            if pair.strip():
                key, value = pair.split("=")
                params[key.strip().lower()] = value.strip()
        return params

    def stop(self):
        """
        Stop the periodic health checks.
        """
        if self.timer:
            self.timer.cancel()
        self.logger.info("HealthChecker stopped.")
