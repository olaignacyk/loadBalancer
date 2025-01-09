from unittest.mock import patch, MagicMock
from loadbalancer import LoadBalancer
from strategies.round_robin import RoundRobinStrategy
from strategies.least_connections import LeastConnectionsStrategy


def test_round_robin_strategy():
    databases = [
        {"Name": "db1", "ConnectionString": "mock_conn1"},
        {"Name": "db2", "ConnectionString": "mock_conn2"}
    ]
    strategy = RoundRobinStrategy()

    assert strategy.select_database(databases)["Name"] == "db1"
    assert strategy.select_database(databases)["Name"] == "db2"
    assert strategy.select_database(databases)["Name"] == "db1"  # Cykl zaczyna się od nowa


def test_least_connections_strategy():
    databases = [
        {"Name": "db1", "ConnectionString": "mock_conn1"},
        {"Name": "db2", "ConnectionString": "mock_conn2"}
    ]
    strategy = LeastConnectionsStrategy()

    # Początkowo obie bazy mają 0 połączeń
    assert strategy.select_database(databases)["Name"] == "db1"  # db1 wybrana (pierwsza w kolejności przy remisie)
    assert strategy.connections_count["db1"] == 1  # Liczba połączeń dla db1 wzrosła
    assert strategy.connections_count["db2"] == 0  # db2 nadal ma 0 połączeń

    # Teraz db2 ma mniej połączeń, więc zostanie wybrana
    assert strategy.select_database(databases)["Name"] == "db2"
    assert strategy.connections_count["db1"] == 1  # db1 nie zmienia liczby połączeń
    assert strategy.connections_count["db2"] == 1  # db2 wzrosło do 1

    # Ponownie db1 i db2 mają tyle samo, więc db1 (pierwsza w kolejności) zostanie wybrana
    assert strategy.select_database(databases)["Name"] == "db1"
    assert strategy.connections_count["db1"] == 2  # Liczba połączeń dla db1 wzrosła do 2
    assert strategy.connections_count["db2"] == 1  # db2 pozostaje na 1

    # Test zwalniania połączeń
    strategy.release_connection("db1")
    assert strategy.connections_count["db1"] == 1  # Liczba połączeń dla db1 zmniejszona
    strategy.release_connection("db2")
    assert strategy.connections_count["db2"] == 0  # Liczba połączeń dla db2 zmniejszona

    # Jeśli db2 ma 0 połączeń, a db1 ma 1, db2 powinna być wybrana
    assert strategy.select_database(databases)["Name"] == "db2"


@patch("psycopg2.connect")
def test_load_balancer_get_connection(mock_connect):
    mock_connection = MagicMock()
    mock_connect.return_value = mock_connection

    load_balancer = LoadBalancer("../Connection/db.json", strategy_type="random")
    conn, db_name = load_balancer.get_connection()

    assert conn == mock_connection
    assert db_name is not None
