var game_board, board_size, last_change = null, timeout_handle;
var player_positions = []

function init_game_board() {
    game_board = document.getElementById('game-board');
    while (game_board.children.length > 0) {
        game_board.removeChild(game_board.children[0]);
    }
    board_size = document.getElementById('input-size').value;
    for (var i = 0; i < board_size; i++) {
        var row = document.createElement('div');
        row.classList.add('row');
        for (var j = 0; j < board_size; j++) {
            var cell = document.createElement('div');
            cell.classList.add('cell');
            cell.id = 'cell-' + i + '-' + j;
            cell.addEventListener('click', function () {
                var result = /cell-(\d+)-(\d+)/.exec(this.id), row, col;
                row = Number.parseInt(result[1]);
                col = Number.parseInt(result[2]);
                for (var i = 0; i < player_positions.length; i++) {
                    if (player_positions[i][0] == row && player_positions[i][1] == col) {
                        // already in player_postion. click to remove
                        player_positions.splice(i, 1);
                        update_game_board();
                        return;
                    }
                }
                // not in player_postion. click to add
                player_positions.push([row, col]);
                update_game_board();
            });
            row.appendChild(cell);
        }
        game_board.appendChild(row);
    }
    player_positions.length = 0;
    player_positions.push([0, 0]);
    player_positions.push([board_size - 1, board_size - 1]);
    update_game_board();
}

function update_game_board() {
    for (var i = 0; i < board_size; i++) {
        for (var j = 0; j < board_size; j++) {
            game_board.children[i].children[j].classList.remove('chosen');
            game_board.children[i].children[j].innerText = '';
        }
    }
    for (var i = 0; i < player_positions.length; i++) {
        var row_col = player_positions[i], row, col;
        row = row_col[0];
        col = row_col[1];
        game_board.children[row].children[col].classList.add('chosen');
        game_board.children[row].children[col].innerText = String(i + 1);
    }
}

window.addEventListener('load', function (ev) {
    document.getElementById('input-size').addEventListener('change', function (ev1) {
        var now = new Date().getTime();
        if (last_change != null) {
            clearTimeout(timeout_handle);
        }
        timeout_handle = setTimeout(init_game_board, 1000);
        last_change = now;
    });
    document.getElementsByTagName('form')[0].addEventListener('submit', function (ev1) {
        document.getElementsByName('player-positions')[0].value = JSON.stringify(player_positions);
    })
    init_game_board();
    try {
        player_positions = JSON.parse(document.getElementsByName('player-positions')[0].value);
        update_game_board();
    } catch (e) {}
});
