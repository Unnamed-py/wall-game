import atexit
import base64
import hashlib
import secrets
import sqlite3
import string
from typing import *


class UserValidationError(ValueError):
    pass


class Storage:
    def __init__(self, filename: str = 'db.sqlite3'):
        self.filename: str = filename
        self.conn = sqlite3.connect(filename)
        atexit.register(self.save)

    def get_user(self, name) -> 'User':
        try:
            data = self.conn.execute('SELECT name, symbol, password FROM User WHERE name=?', (name,)).fetchall()
            return User(*data[0])
        except IndexError:
            raise UserValidationError("用户不存在")

    def update_user(self, user: 'User'):
        try:
            self.conn.execute('UPDATE User SET name=?, symbol=?, password=? WHERE name=?',
                              (user.name, user.symbol, user.password, user.name))
        except sqlite3.IntegrityError as exc:
            if 'symbol' in exc:
                raise UserValidationError("符号已被其他用户占用")
            elif 'name' in exc:
                raise UserValidationError("用户名已被其他用户占用")

    def new_user(self, user: 'User'):
        try:
            self.conn.execute('INSERT INTO User (name, symbol, password) VALUES (?, ?, ?)',
                              (user.name, user.symbol, user.password))
        except sqlite3.IntegrityError as exc:
            if 'symbol' in exc.args[0]:
                raise UserValidationError("符号已被其他用户占用")
            elif 'name' in exc.args[0]:
                raise UserValidationError("用户名已被其他用户占用")

    def save(self):
        self.conn.commit()


class User:
    __slots__ = '_name', '_symbol', 'pwd_method', 'pwd_salt', 'pwd_digest'
    name_chars = string.ascii_letters + string.digits + '-_'
    name_charset = set(name_chars)
    symbol_charset = set(string.printable.strip())

    def __init__(self, name: str, symbol: str, password: Optional[str] = None, raw_password: Optional[str] = None):
        self.name = name
        self.symbol = symbol
        if password is not None:
            self.password = password
        elif raw_password is not None:
            self.set_password(raw_password)
        else:
            raise ValueError("neither 'password' nor 'raw_password' is given")

    @property
    def password(self):
        return f'{self.pwd_method}:{self.pwd_salt.decode()}:{base64.b64encode(self.pwd_digest).decode()}'

    @password.setter
    def password(self, value):
        method, salt, digest = value.split(':')
        self.pwd_method = method
        self.pwd_salt = salt.encode()
        self.pwd_digest = base64.b64decode(digest.encode())

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        if not 1 <= len(value) <= 20:
            raise UserValidationError('用户名长度必须在闭区间1到20之间')
        if not all(char in self.name_charset for char in value):
            raise UserValidationError(f'用户名只能包含字符{self.name_chars}')

        self._name = value

    @property
    def symbol(self):
        return self._symbol

    @symbol.setter
    def symbol(self, value):
        if (len(value) == 2 and all(char in self.symbol_charset for char in value)) or \
                (len(value) == 1 and value.strip()):
            self._symbol = value
        else:
            raise UserValidationError('符号必须为一个全角字符或一到两个ascii字符')

    def verify_password(self, raw_password):
        ha = hashlib.new(self.pwd_method, self.pwd_salt)
        ha.update(raw_password.encode() if isinstance(raw_password, str) else raw_password)
        return ha.digest() == self.pwd_digest

    def set_password(self, raw_password, method='sha256'):
        if not 4 <= len(raw_password) <= 60:
            raise UserValidationError('密码长度必须在闭区间4到60之间')
        salt = bytes(secrets.choice(self.salt_choices) for _ in range(4))
        ha = hashlib.new(method, salt)
        ha.update(raw_password.encode() if isinstance(raw_password, str) else raw_password)
        self.pwd_method = method
        self.pwd_salt = salt
        self.pwd_digest = ha.digest()

    def __eq__(self, o: 'User') -> bool:
        return self.name == o.name

    def __hash__(self) -> int:
        return hash(self.name)

    salt_choices = (string.ascii_letters + string.digits).encode()
