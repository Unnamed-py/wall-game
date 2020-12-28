import itertools
from collections import deque, Counter
from enum import Enum
import traceback


class Direction(Enum):
    left = 'l'
    right = 'r'
    up = 'u'
    down = 'd'


class Event(Enum):
    update_game_map = 'update_game_map'
    ask_player_action = 'ask_player_action'
    player_out = 'player_out'


class Player:
    __slots__ = ['row', 'col', 'symbol', 'status']

    def __init__(self, symbol, row, col) -> None:
        self.symbol = symbol
        self.row = row
        self.col = col
        self.status = 'normal'  # 'normal' or 'out'

    def __eq__(self, o):
        return self.symbol == getattr(o, 'symbol', None)

    def __repr__(self) -> str:
        return f'<{self.symbol} at ({self.row}, {self.col})>'

    def __hash__(self):
        return hash(self.symbol)


class WallGame:
    def __init__(self, size=7, players=None):
        self.size = size
        self.wall_left = [[False] * size for _ in range(size)]
        self.wall_top = [[False] * size for _ in range(size)]
        self.players = players or [Player('甲', 0, 0),
                                   Player('乙', size - 1, size - 1)]
        self.areas = 1
        self.area_sizes = [0, size * size]
        self.map = [[1] * size for _ in range(size)]
        for i in range(size):
            self.wall_left[i][0] = True
            self.wall_top[0][i] = True

    def find_player_by_pos(self, row, col):
        for player in self.players:
            if player.row == row and player.col == col:
                return player
        return None

    def update_areas(self):
        # 将对象属性变为局部变量可以加快访问速度
        size = self.size
        map = self.map
        area_sizes = self.area_sizes
        # 清楚地图区域标记
        for i in range(size):
            map[i][:] = itertools.repeat(0, size)
        areas = 0
        area_sizes.clear()
        # 列表索引从0开始，而area从1开始，故先放入一个0作为占位符
        area_sizes.append(0)
        for i in range(self.size):
            for j in range(self.size):
                if map[i][j] == 0:
                    areas += 1
                    map[i][j] = areas
                    area_sizes.append(1)
                    queue = deque(((i, j),))
                    while queue:
                        row, col = queue.popleft()
                        for r, c in self.reachable_points_near(row, col):
                            if map[r][c] == 0:
                                map[r][c] = areas
                                queue.append((r, c))
                                area_sizes[areas] += 1
        self.map = map

    def get_reachable_points(self, player: Player):
        queue = deque(((player.row, player.col, 0),))
        yield player.row, player.col
        while queue:
            row, col, step = queue.popleft()
            yield row, col
            if step >= 3:
                continue
            for r, c in self.reachable_points_near(row, col):
                if self.find_player_by_pos(r, c) in (None, player):
                    queue.append((r, c, step + 1))

    def reachable_points_near(self, row, col):
        wall_top = self.wall_top
        wall_left = self.wall_left
        if row > 0 and wall_top[row][col] is False:
            yield row - 1, col
        if col > 0 and wall_left[row][col] is False:
            yield row, col - 1
        if row < self.size - 1 and wall_top[row + 1][col] is False:
            yield row + 1, col
        if col < self.size - 1 and wall_left[row][col + 1] is False:
            yield row, col + 1

    def put_wall(self, player_pos, direction: Direction):
        wall_list, row, col = {
            Direction.up: (self.wall_top, player_pos[0], player_pos[1]),
            Direction.down: (self.wall_top, player_pos[0] + 1, player_pos[1]),
            Direction.left: (self.wall_left, player_pos[0], player_pos[1]),
            Direction.right: (self.wall_left, player_pos[0], player_pos[1] + 1)
        }[direction]
        try:
            if wall_list[row][col] is False:
                wall_list[row][col] = True
            else:
                raise ValueError('there is already a wall')
        except IndexError:
            raise ValueError('there is already a wall')

    def apply_player_action(self, player, motions, wall_dir):
        reachable_points = self.get_reachable_points(player)
        new_pos = player.row + motions[0], player.col + motions[1]
        if new_pos in reachable_points:
            self.put_wall(new_pos, wall_dir)
            player.row = new_pos[0]
            player.col = new_pos[1]
        else:
            raise ValueError('invalid motions')

    def game_loop(self):
        try:
            player_cycle = itertools.cycle(self.players)
            remaining_players = len(self.players)
            yield Event.update_game_map,
            while remaining_players > 1:
                player = next(player_cycle)
                if player.status == 'out':
                    continue
                message = ''
                while True:
                    motions, wall_dir = yield Event.ask_player_action, player, message
                    try:
                        self.apply_player_action(player, motions, wall_dir)
                    except ValueError as error:
                        message = error.args[0]
                    else:
                        break
                self.update_areas()
                yield Event.update_game_map,

                # 检查是否有人出局
                areas_players = Counter(self.map[player.row][player.col]
                                        for player in self.players)
                for p in self.players:
                    if areas_players[self.map[p.row][p.col]] == 1:
                        if p.status == 'normal':
                            yield Event.player_out, p, self.area_sizes[self.map[p.row][p.col]]
                            remaining_players -= 1
        except:
            traceback.print_exc()
        return {player: self.area_sizes[self.map[player.row][player.col]]
                for player in self.players}
