from strategies.base_strategy import LoadBalancingStrategy


class LeastConnectionsStrategy(LoadBalancingStrategy):
    def __init__(self):
        self.connections_count = {}

    def select_database(self, databases):
        if not databases:
            return None

        for db in databases:
            if db['Name'] not in self.connections_count:
                self.connections_count[db['Name']] = 0

        selected_db = min(databases, key=lambda db: self.connections_count[db['Name']])
        self.connections_count[selected_db['Name']] += 1
        return selected_db

    def release_connection(self, db_name):
        """Decrement the connection count for the given database."""
        if db_name in self.connections_count and self.connections_count[db_name] > 0:
            self.connections_count[db_name] -= 1
