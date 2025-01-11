import re
import threading
import time
from loadbalancer import LoadBalancer
from observer.health_checker import HealthChecker
import json
import random


def validate_name(name):
    """
    Validate that the name contains both first and last name, each starting with a capital letter.
    """
    if not name.strip():
        return False
    parts = name.split()
    return len(parts) == 2 and all(part.istitle() for part in parts)


def validate_email(email):
    """
    Validate that the email has a proper format.
    """
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def monitor_new_databases(load_balancer, config_file, interval=60):
    """
    Regularly check for new databases in the configuration file and add them if necessary.
    """
    while True:
        with open(config_file, 'r') as file:
            all_databases = json.load(file)

        for db in all_databases:
            if db["Name"] not in [d["Name"] for d in load_balancer.databases]:
                load_balancer.add_database(db)

        time.sleep(interval)


def main():
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
    load_balancer.reset_sequences()

    # Inicjalizacja Health Checkera
    with open('Connection/db.json', 'r') as file:
        databases = json.load(file)
    health_checker = HealthChecker(databases, check_interval=15)

    # Rejestracja Load Balancera jako obserwatora
    health_checker.add_observer(load_balancer)

    # Uruchomienie Health Checkera w tle
    health_checker.check_health()

    # Uruchomienie monitora nowych baz danych w oddzielnym wątku
    monitor_thread = threading.Thread(target=monitor_new_databases, args=(load_balancer, 'Connection/db.json', 60), daemon=True)
    monitor_thread.start()

    try:
        while True:
            print("\n--- Menu Operacji ---")
            print("1. Wyświetl użytkownika po ID (SELECT)")
            print("2. Wyświetl wszystkich użytkowników (SELECT ALL)")
            print("3. Dodaj nowego użytkownika (INSERT)")
            print("4. Dodaj losowego użytkownika (INSERT RANDOM)")
            print("5. Usuń użytkownika po ID (DELETE)")
            print("6. Zaktualizuj użytkownika po ID (UPDATE)")
            print("7. Zmień algorytm load balancing")
            print("8. Wyjście")

            choice = input("Wybierz operację: ")
            if choice == "1":  # SELECT po ID
                user_id = input("Podaj ID użytkownika: ")
                query = "SELECT * FROM users WHERE id = %s;"
                results = load_balancer.execute_select(query, (user_id,))
                if results:
                    for row in results:
                        print(f"ID: {row[0]}, Name: {row[1]}, Email: {row[2]}")
                else:
                    print("Nie znaleziono użytkownika o podanym ID.")

            elif choice == "2":  # SELECT ALL
                query = "SELECT * FROM users;"
                results = load_balancer.execute_select(query)
                print("\n--- Lista Użytkowników ---")
                for row in results:
                    print(f"ID: {row[0]}, Name: {row[1]}, Email: {row[2]}")

            elif choice == "3":  # INSERT
                while True:
                    name = input("Podaj imię i nazwisko (np. Jan Kowalski): ")
                    if validate_name(name):
                        break
                    print("Nieprawidłowe imię i nazwisko. Musisz podać imię i nazwisko, zaczynające się wielkimi literami.")

                while True:
                    email = input("Podaj email: ")
                    if validate_email(email):
                        break
                    print("Nieprawidłowy format email. Spróbuj ponownie (np. example@example.com).")

                load_balancer.add_user(name, email)
                print("Dodano nowego użytkownika.")

            elif choice == "4":  # INSERT RANDOM
                chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
                random_name = " ".join(["".join(random.choices(chars, k=5)).capitalize() for _ in range(2)])
                random_email = f"{random_name.split()[0].lower()}@example.com"
                load_balancer.add_user(random_name, random_email)
                print(f"Dodano losowego użytkownika: {random_name}, {random_email}")

            elif choice == "5":  # DELETE
                user_id = input("Podaj ID użytkownika do usunięcia: ")
                load_balancer.delete_user(int(user_id))

            elif choice == "6":  # UPDATE
                user_id = input("Podaj ID użytkownika do zaktualizowania: ")
                new_name = input("Podaj nowe imię i nazwisko (lub naciśnij Enter, aby pominąć): ")
                if new_name and not validate_name(new_name):
                    print("Nieprawidłowe imię i nazwisko. Zmiana została pominięta.")
                    new_name = None

                new_email = input("Podaj nowy email (lub naciśnij Enter, aby pominąć): ")
                if new_email and not validate_email(new_email):
                    print("Nieprawidłowy format email. Zmiana została pominięta.")
                    new_email = None

                load_balancer.update_user(int(user_id), name=new_name or None, email=new_email or None)

            elif choice == "7":  # Zmień algorytm load balancing
                print("Wybierz algorytm: 1 - RoundRobin, 2 - Random, 3 - LeastConnections")
                algorithm_choice = input("Wybór: ")
                if algorithm_choice == "1":
                    load_balancer.set_strategy("round_robin")
                    print("Algorytm zmieniony na RoundRobin.")
                elif algorithm_choice == "2":
                    load_balancer.set_strategy("random")
                    print("Algorytm zmieniony na Random.")
                elif algorithm_choice == "3":
                    load_balancer.set_strategy("least_connections")
                    print("Algorytm zmieniony na LeastConnections.")
                else:
                    print("Nieprawidłowy wybór algorytmu.")

            elif choice == "8":  # Wyjście
                print("Zamykanie programu...")
                break

            else:
                print("Nieprawidłowy wybór. Spróbuj ponownie.")

    except KeyboardInterrupt:
        print("\nPrzerwano program.")
    finally:
        health_checker.stop()


if __name__ == "__main__":
    main()
