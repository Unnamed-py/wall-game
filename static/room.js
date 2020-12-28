var ws;
var room_size;
var current_player;
var ws;
var waiting_action;
var reachable_points;
var chosen_pos;

function put_message(message) {
    var ele = document.createElement('div');
    ele.classList.add('message');
    ele.innerText = message
    var message_display = document.getElementById('message-display');
    message_display.appendChild(ele);
}

function set_status_text(text) {
    document.getElementById('status-display').innerText = text;
}

function init_room(size) {
    game_board = document.getElementById('game-board');
    room_size = size;
    waiting_action = false;
    for (var i = 0; i < size; i++) {
        var row = document.createElement('div');
        row.classList.add('row');
        for (var j = 0; j < size; j++) {
            var cell = document.createElement('div');
            cell.classList.add('cell');
            cell.id = 'cell-' + i + '-' + j;
            row.appendChild(cell);
        }
        game_board.appendChild(row);
    }
    var ws_url = location.href.endsWith('/') ? location.href + 'ws/' : location.href + '/ws/';
    ws_url = ws_url.replace('http://', 'ws://').replace('https://', 'wss://');
    ws = new WebSocket(ws_url);
    set_status_text('等待玩家');
    ws.onmessage = function (e) {
        var data = JSON.parse(e.data);
        if (data.event == 'joined') {
            if (!data.successful) {
                alert('加入房间失败！可能房间已满！');
                location.href = document.referrer;
            } else {
                current_player = data.player;
                put_message('您已加入房间，您的符号是：' + current_player);
            }
        } else if (data.event == 'new_player') {
            put_message('符号为 ' + data.player + ' 的玩家已加入房间');
        } else if (data.event == 'game_start') {
            put_message('游戏开始！');
            set_status_text('游戏进行中');
        } else if (data.event == 'game_over') {
            put_message('游戏结束！');
            set_status_text('游戏已结束');
            players_scores = data.result;
            var last_rank, last_score, output = [], rank;
            for (var i = 0; i < players_scores.length; i++) {
                if (players_scores[i][1] == last_score) {
                    rank = last_rank;
                } else {
                    rank = i + 1;
                }
                output.push(rank + '. ' + players_scores[i][0] + ' ' + players_scores[i][1]);
                last_rank = rank;
                last_score = players_scores[i][1];
            }
            put_message('游戏排名：\n' + output.join('\n'));
        } else if (data.event == 'update_game_map') {
            var game_board = document.getElementById('game-board');
            function add_class(cell, class_) {
                if (!cell.classList.contains(class_)) {
                    cell.classList.add(class_);
                }
            }
            for (var i = 0; i < size; i++) {
                var row = game_board.children[i];
                for (var j = 0; j < size; j++) {
                    var cell = row.children[j];
                    cell.innerText = '';
                    if (data.wall_top[i][j] == '1') {
                        add_class(cell, 'cell-wall-top');
                    }
                    if (data.wall_left[i][j] == '1') {
                        add_class(cell, 'cell-wall-left');
                    }
                    if (data.wall_top[i + 1] == null || data.wall_top[i + 1][j] == '1') {
                        add_class(cell, 'cell-wall-bottom');
                    }
                    if (data.wall_left[i][j + 1] == '1' || data.wall_left[i][j + 1] == null) {
                        add_class(cell, 'cell-wall-right');
                    }
                }
            }
            var row, col, player;
            for (var i = 0; i < data.players_info.length; i++) {
                row = data.players_info[i][0];
                col = data.players_info[i][1];
                player = data.players_info[i][2];
                game_board.children[row].children[col].innerText = player;
            }
        } else if (data.event == 'player_out') {
            if (data.player == current_player) {
                put_message('您（' + data.player + '）已出局');
            } else {
                put_message('玩家 ' + data.player + ' 已出局');
            }
        } else if (data.event == 'ask_player_action') {
            game_board = document.getElementById('game-board');
            waiting_action = true;
            var row, col;
            reachable_points = data.reachable_points;
            for (var i = 0; i < reachable_points.length; i++) {
                row = reachable_points[i][0];
                col = reachable_points[i][1];
                game_board.children[row].children[col].classList.add('cell-reachable');
                game_board.children[row].children[col].onclick = function (e) {
                    var row, col;
                    game_board = document.getElementById('game-board');
                    if (chosen_pos) {
                        var last_chosen = game_board.children[chosen_pos[0]].children[chosen_pos[1]];
                        while (last_chosen.children.length > 0) {
                            last_chosen.removeChild(last_chosen.children[0]);
                        }
                    }
                    row = parseInt(this.id.split('-')[1]);
                    col = parseInt(this.id.split('-')[2]);
                    chosen_pos = [row, col];

                }
            }
        }
    }
}
