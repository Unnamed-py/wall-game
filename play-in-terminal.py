import os
import core
try:
    size = int(input('size (default 7): '))
except ValueError:
    size = 7
game = core.WallGame(size)

game_loop = game.game_loop()
reply = None
try:
    while True:
        event, *args = game_loop.send(reply)

        if event is core.Event.update_game_map:
            pos_sym_dict = {(player.row, player.col): player.symbol
                            for player in game.players}
            os.system('cls' if os.name == 'nt' else 'clear')
            for i in range(game.size):
                print('+' + '+'.join(('--' if value else '  ')
                                     for value in game.wall_top[i]) + '+')
                print(''.join((
                    ('|' if game.wall_left[i][j] else ' ') +
                    pos_sym_dict.get((i, j), '  ')
                    for j in range(game.size))) + '|')
            print('+' + '--+' * game.size)

        elif event is core.Event.ask_player_action:
            player, message = args
            while True:
                if message:
                    print(f'= Error: {message}')
                action = input(f'= player {player.symbol}, '
                               'input move directions (WASD) and wall directions (IJKL)\n= > ').upper()
                move_row = 0
                move_col = 0
                wall_dir = None
                for char in action:
                    if char == 'W':
                        move_row -= 1
                    elif char == 'A':
                        move_col -= 1
                    elif char == 'S':
                        move_row += 1
                    elif char == 'D':
                        move_col += 1
                    elif char in 'IJKL':
                        wall_dir = {
                            'I': core.Direction.up,
                            'J': core.Direction.left,
                            'K': core.Direction.down,
                            'L': core.Direction.right
                        }[char]
                if wall_dir is None:
                    message = 'wall direction is missing'
                    continue

                reply = (move_row, move_col), wall_dir
                break

        elif event is core.Event.player_out:
            player, score = args
            print(f'= player {player.symbol} is out (with score {score})')


except StopIteration as error:
    rank = sorted(error.value.items(), key=lambda x: x[1], reverse=True)
    print('= game over, rank:')
    last_score = None
    last_rank = None
    for rank, (player, score) in enumerate(rank, 1):
        if score == last_score:
            rank = last_rank
        print(f'= {rank}. {player.symbol} (score {score})')
        last_score, last_rank = score, rank
input()
