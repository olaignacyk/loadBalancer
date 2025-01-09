import unittest
import json
import tempfile
from unittest.mock import patch, MagicMock
from loadbalancer import LoadBalancer


class TestLoadBalancerWithTempFile(unittest.TestCase):
    def setUp(self):
        """
        Przygotowanie środowiska testowego.
        """
        self.config_file = "../Connection/db.json"

        # Mockowanie konfiguracji baz danych
        self.mock_databases = [
            {"Name": "db1", "ConnectionString": "Server=localhost;Port=5432;Database=database1;User=user1;Password=password1;"},
            {"Name": "db2", "ConnectionString": "Server=localhost;Port=5433;Database=database2;User=user2;Password=password2;"}
        ]

        # Tworzenie instancji LoadBalancer
        self.load_balancer = LoadBalancer(self.config_file, strategy_type="round_robin")
        self.load_balancer.databases = self.mock_databases

    @patch("psycopg2.connect")
    def test_create_table(self, mock_connect):
        """
        Test metody create_table.
        """
        mock_cursor = MagicMock()
        mock_connection = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_connection

        schema = """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL
        );
        """
        self.load_balancer.create_table(schema)

        # Sprawdzanie czy połączenie było nawiązane do każdej bazy
        self.assertEqual(mock_connect.call_count, len(self.mock_databases))

        # Sprawdzanie czy schemat został przekazany do wykonania
        mock_cursor.execute.assert_called_with(schema)

    @patch("psycopg2.connect")
    def test_insert_data(self, mock_connect):
        """
        Test metody synchronize_tables przy wstawianiu danych.
        """
        mock_cursor = MagicMock()
        mock_connection = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_connection

        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            # Zapisanie początkowych danych
            initial_data = []
            json.dump(initial_data, temp_file)
            temp_file.seek(0)  # Powrót do początku pliku

            # Dodanie nowego użytkownika
            self.load_balancer.add_user(temp_file.name, "Alice Johnson", "alice@example.com")

            # Sprawdzanie, czy zapytanie do wstawiania danych zostało wykonane w każdej bazie
            mock_cursor.execute.assert_called_with(
                "INSERT INTO users (id, name, email) VALUES (%s, %s, %s) ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, email = EXCLUDED.email;",
                (1, "Alice Johnson", "alice@example.com")
            )

    @patch("psycopg2.connect")
    def test_select_data(self, mock_connect):
        """
        Test metody execute_select.
        """
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, "Alice Johnson", "alice@example.com"),
            (2, "John Doe", "john.doe@example.com")
        ]
        mock_connection = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_connection

        query = "SELECT * FROM users;"
        results = self.load_balancer.execute_select(query)

        # Sprawdzanie wyników zapytania SELECT
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], (1, "Alice Johnson", "alice@example.com"))
        self.assertEqual(results[1], (2, "John Doe", "john.doe@example.com"))

        # Sprawdzanie, czy zapytanie zostało wykonane na jednej bazie
        mock_cursor.execute.assert_called_with(query, None)

    @patch("loadbalancer.LoadBalancer.synchronize_tables")
    def test_add_user(self, mock_sync):
        """
        Test metody add_user z użyciem pliku tymczasowego.
        """
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            # Zapisanie początkowych danych
            json.dump([], temp_file)
            temp_file.seek(0)  # Powrót do początku pliku

            # Wywołanie metody add_user
            self.load_balancer.add_user(temp_file.name, "Alice Johnson", "alice@example.com")

            # Sprawdzanie zawartości pliku po dodaniu użytkownika
            temp_file.seek(0)
            data = json.load(temp_file)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["name"], "Alice Johnson")
            self.assertEqual(data[0]["email"], "alice@example.com")

            # Sprawdzanie, czy synchronizacja została wywołana
            mock_sync.assert_called_with(temp_file.name)

    @patch("loadbalancer.LoadBalancer.synchronize_tables")
    def test_update_user(self, mock_sync):
        """
        Test metody update_user z użyciem pliku tymczasowego.
        """
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            # Zapisanie początkowych danych
            initial_data = [{"id": 1, "name": "John Doe", "email": "john.doe@example.com"}]
            json.dump(initial_data, temp_file)
            temp_file.seek(0)  # Powrót do początku pliku

            # Wywołanie metody update_user
            self.load_balancer.update_user(temp_file.name, 1, name="John Updated")

            # Sprawdzanie zawartości pliku po aktualizacji użytkownika
            temp_file.seek(0)
            data = json.load(temp_file)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["name"], "John Updated")
            self.assertEqual(data[0]["email"], "john.doe@example.com")

            # Sprawdzanie, czy synchronizacja została wywołana
            mock_sync.assert_called_with(temp_file.name)

    @patch("loadbalancer.LoadBalancer.synchronize_tables")
    def test_delete_user(self, mock_sync):
        """
        Test metody delete_user z użyciem pliku tymczasowego.
        """
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            # Zapisanie początkowych danych
            initial_data = [{"id": 1, "name": "John Doe", "email": "john.doe@example.com"}]
            json.dump(initial_data, temp_file)
            temp_file.seek(0)  # Powrót do początku pliku

            # Wywołanie metody delete_user
            self.load_balancer.delete_user(temp_file.name, 1)

            # Sprawdzanie zawartości pliku po usunięciu użytkownika
            temp_file.seek(0)
            data = json.load(temp_file)
            self.assertEqual(len(data), 0)  # Plik powinien być pusty

            # Sprawdzanie, czy synchronizacja została wywołana
            mock_sync.assert_called_with(temp_file.name)


if __name__ == "__main__":
    unittest.main()
