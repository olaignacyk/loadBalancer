from loadbalancer import LoadBalancer
from observer.health_checker import HealthChecker
import json

if __name__ == "__main__":
    # Inicjalizacja Load Balancera
    load_balancer = LoadBalancer('Connection/db.json', strategy_type="least_connections")

    # Wczytanie konfiguracji baz danych
    with open('Connection/db.json', 'r') as file:
        databases = json.load(file)

    # Inicjalizacja Health Checkera
    health_checker = HealthChecker(databases, check_interval=15)

    # Rejestracja Load Balancera jako obserwatora
    health_checker.add_observer(load_balancer)

    # Uruchomienie Health Checkera w tle
    health_checker.check_health()

    try:
        # Symulacja zapytań do Load Balancera
        active_connections = []
        for _ in range(5):  # Symulacja 5 żądań
            conn, db_name = load_balancer.get_connection()
            if conn:
                active_connections.append((conn, db_name))
                print(f"Performing operation on database {db_name}")

        # Zwolnienie połączeń
        for conn, db_name in active_connections:
            conn.close()
            load_balancer.release_connection(db_name)

    except KeyboardInterrupt:
        print("Shutting down gracefully...")
    finally:
        # Zatrzymanie Health Checkera
        health_checker.stop()
