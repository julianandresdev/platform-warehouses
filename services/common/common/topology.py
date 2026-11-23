"""Declare the shared RabbitMQ topology and exit."""

from common.rabbit import connect, declare_topology


def main() -> None:
    connection = connect()
    try:
        declare_topology(connection.channel())
    finally:
        connection.close()


if __name__ == "__main__":
    main()
