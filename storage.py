import atexit
import sqlite3


class Storage:
    def __init__(self, filename: str):
        self.filename: str = filename
        self.conn = sqlite3.connect(filename)
        atexit.register(self.save)

    def save(self):
        self.conn.commit()


class User:
    __slots__ = 'name', 'symbol', 'password'

    def __init__(self, name: str, symbol: str, password: str):
        self.name = name
        self.symbol = symbol
        self.password = password

    def __eq__(self, o: 'User') -> bool:
        return self.name == o.name

    def __hash__(self) -> int:
        return hash(self.name)
