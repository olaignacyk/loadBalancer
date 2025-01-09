import unittest
from unittest.mock import MagicMock
from observer.health_checker import HealthChecker
from loadbalancer import LoadBalancer
import json


class TestObserver(unittest.TestCase):
    def setUp(self):
        # Wczytaj konfigurację z pliku db.json
        with open("../Connection/db.json", "r") as file:
            self.databases = json.load(file)

        # Tworzenie obiektu HealthChecker
        self.health_checker = HealthChecker(self.databases, check_interval=10)

        # Mockowanie loggera w LoadBalancer (aby nie generować logów w trakcie testów)
        LoadBalancer.logger = MagicMock()

        # Tworzenie obiektu LoadBalancer
        self.load_balancer = LoadBalancer("../Connection/db.json", strategy_type="least_connections")

        # Rejestracja LoadBalancer jako obserwatora
        self.health_checker.add_observer(self.load_balancer)

    def test_health_checker_notifies_observer(self):
        # Symulacja powiadomienia o tym, że baza "db1" jest "unhealthy"
        self.health_checker.notify_observers("db1", "unhealthy")

        # Sprawdzenie, czy baza "db1" została usunięta z LoadBalancer
        databases_names = [db["Name"] for db in self.load_balancer.databases]
        self.assertNotIn("db1", databases_names)

        # Symulacja powiadomienia o tym, że baza "db1" jest "healthy"
        self.health_checker.notify_observers("db1", "healthy")

        # Sprawdzenie, czy baza "db1" została ponownie dodana do LoadBalancer
        databases_names = [db["Name"] for db in self.load_balancer.databases]
        self.assertIn("db1", databases_names)

    def test_no_notification_for_unknown_database(self):
        # Symulacja powiadomienia dla bazy, która nie istnieje
        self.health_checker.notify_observers("db3", "unhealthy")

        # Sprawdzenie, że nic się nie zmieniło w LoadBalancer
        databases_names = [db["Name"] for db in self.load_balancer.databases]
        self.assertIn("db1", databases_names)
        self.assertIn("db2", databases_names)

    def test_health_checker_calls_observer_methods(self):
        # Mockowanie metody update w LoadBalancer
        self.load_balancer.update = MagicMock()

        # Symulacja powiadomienia
        self.health_checker.notify_observers("db1", "unhealthy")

        # Sprawdzenie, czy metoda update została wywołana w LoadBalancer
        self.load_balancer.update.assert_called_once_with("db1", "unhealthy")


if __name__ == "__main__":
    unittest.main()
