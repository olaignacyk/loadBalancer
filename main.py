import re
from loadbalancer import LoadBalancer
from observer.health_checker import HealthChecker
import json
import random


def validate_name(name):
    if not name.strip():
        return False
    parts = name.split()
    return len(parts) == 2 and all(part.istitle() for part in parts)


def validate_email(email):
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def main():
    load_balancer = LoadBalancer('Connection/db.json', strategy_type="least_connections")

    schema = """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL
    );
    """
    load_balancer.create_table(schema)
    load_balancer.reset_sequences()

    with open('Connection/db.json', 'r') as file:
        databases = json.load(file)
    health_checker = HealthChecker(databases, check_interval=15)

    health_checker.add_observer(load_balancer)
    health_checker.check_health()

    load_balancer.synchronize_tables()

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

            if choice == "1":
                user_id = input("Podaj ID użytkownika: ")
                query = "SELECT * FROM users WHERE id = %s;"
                results = load_balancer.execute_select(query, (user_id,))
                if results:
                    for row in results:
                        print(f"ID: {row[0]}, Name: {row[1]}, Email: {row[2]}")
                else:
                    print("Nie znaleziono użytkownika o podanym ID.")

            elif choice == "2":
                query = "SELECT * FROM users ORDER BY id;"
                results = load_balancer.execute_select(query)
                for row in results:
                    print(f"ID: {row[0]}, Name: {row[1]}, Email: {row[2]}")

            elif choice == "3":
                while True:
                    name = input("Podaj imię i nazwisko: ")
                    if validate_name(name):
                        break
                    print("Nieprawidłowe imię i nazwisko.")

                while True:
                    email = input("Podaj email: ")
                    if validate_email(email):
                        break
                    print("Nieprawidłowy format email.")

                query = "INSERT INTO users (name, email) VALUES (%s, %s);"
                load_balancer.execute_non_select_query(query, (name, email))
                print("Dodano nowego użytkownika.")

            elif choice == "4":
                chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
                random_name = " ".join(["".join(random.choices(chars, k=5)).capitalize() for _ in range(2)])
                random_email = f"{random_name.split()[0].lower()}@example.com"
                query = "INSERT INTO users (name, email) VALUES (%s, %s);"
                load_balancer.execute_non_select_query(query, (random_name, random_email))
                print(f"Dodano losowego użytkownika: {random_name}, {random_email}")

            elif choice == "5":
                user_id = input("Podaj ID użytkownika do usunięcia: ")
                query_check = "SELECT 1 FROM users WHERE id = %s LIMIT 1;"
                results = load_balancer.execute_select(query_check, (user_id,))
                if not results:
                    print(f"Użytkownik o ID {user_id} nie istnieje.")
                    continue

                query = "DELETE FROM users WHERE id = %s;"
                load_balancer.execute_non_select_query(query, (user_id,))
                print(f"Użytkownik o ID {user_id} został usunięty.")

            elif choice == "6":  # UPDATE
                user_id = input("Podaj ID użytkownika do zaktualizowania: ")
                query_check = "SELECT 1 FROM users WHERE id = %s LIMIT 1;"
                results = load_balancer.execute_select(query_check, (user_id,))

                if not results:
                    print(f"Użytkownik o ID {user_id} nie istnieje.")
                    continue

                new_name = None
                while True:
                    new_name = input("Podaj nowe imię i nazwisko (lub naciśnij Enter, aby pominąć): ")
                    if not new_name:  # Puste wejście oznacza pominięcie
                        break
                    if validate_name(new_name):
                        break
                    print("Nieprawidłowe imię i nazwisko.")

                new_email = None
                while True:
                    new_email = input("Podaj nowy email (lub naciśnij Enter, aby pominąć): ")
                    if not new_email:  # Puste wejście oznacza pominięcie
                        break
                    if validate_email(new_email):
                        break
                    print("Nieprawidłowy format email. Spróbuj ponownie (np. example@example.com).")
                if not new_name and not new_email:
                    print("Brak danych do zaktualizowania. Operacja została anulowana.")
                    continue

                query = "UPDATE users SET "
                params = []
                if new_name:
                    query += "name = %s, "
                    params.append(new_name)
                if new_email:
                    query += "email = %s, "
                    params.append(new_email)

                query = query.rstrip(", ") + " WHERE id = %s;"
                params.append(user_id)
                load_balancer.execute_non_select_query(query, params)
                print(f"Użytkownik o ID {user_id} został zaktualizowany.")

            elif choice == "7":
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

            elif choice == "8":
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
