from loadbalancer import LoadBalancer
from observer.health_checker import HealthChecker
import json

if __name__ == "__main__":
    # Inicjalizacja Load Balancera
    load_balancer = LoadBalancer('Connection/db.json', strategy_type="least_connections")

    # Tworzenie tabeli w każdej bazie danych
    schema = """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL
    );
    """
    load_balancer.create_table(schema)

    # Synchronizacja danych z pliku master_data.json
    master_file = "data/master_data.json"
    load_balancer.synchronize_tables(master_file)

    # Inicjalizacja Health Checkera
    with open('Connection/db.json', 'r') as file:
        databases = json.load(file)
    health_checker = HealthChecker(databases, check_interval=15)

    # Rejestracja Load Balancera jako obserwatora
    health_checker.add_observer(load_balancer)

    # Uruchomienie Health Checkera w tle
    health_checker.check_health()

    try:
        # Demonstracja operacji na danych
        print("\n--- Operacje na danych ---")

        # 1. SELECT
        print("Aktualna zawartość tabeli `users`:")
        select_query = "SELECT * FROM users;"
        results = load_balancer.execute_select(select_query)
        for row in results:
            print(row)

    except KeyboardInterrupt:
        print("Shutting down gracefully...")
    finally:
        # Zatrzymanie Health Checkera
        health_checker.stop()
